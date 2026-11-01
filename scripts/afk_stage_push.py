"""AFK stage push: fight stage after stage, verified by screen state.

Each victory raises AFK Progress by one stage and permanently increases the AFK
income rate. Battles are free (no attempts, no resources), they just take ~90 s
of what looks like auto-combat, so this loop is safe to run while idle.

Flow: PREP/VICTORY (green Battle button at (1280,1000)) -> BATTLE -> VICTORY ->
repeat. Stops on DEFEAT (stage too hard) or when the requested count is reached,
and always leaves the game on the result screen (no stray taps).

Usage: python scripts/afk_stage_push.py [--battles N] [--max-battle-seconds 150]
Exit codes: 0 finished/pushed, 1 stuck (unknown screen), 2 memory preflight,
5 skipped (PC in use).
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
SKIP_BTN = (1220, 788)       # verified: skips the running fight instantly to PREP/RESULT
AFK_PROGRESS = (60, 1036)
OCR_PS1 = REPO / "templates" / "ocr.ps1"
WALL_LOG = REPO / ".spectre" / "wall-report.log"
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def classify_battle(img) -> str:
    dark = v.lum(v.avg(img, (960, 300)))
    header = v.lum(v.avg(img, (960, 40)))
    arena = v.avg(img, (960, 400))
    card = v.lum(v.avg(img, (960, 300)))
    search = v.lum(v.avg(img, (960, 124)))
    # Theme-independent battle marker: the pause button is dark during a fight
    # (L~44 day and night) while prep ground is bright (L~147) and result cards
    # are very bright (L~238). The arena colour alone is unreliable — stages use
    # different day/night themes.
    pause = v.lum(v.avg(img, (549, 846)))
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
    if search > 120 and dark < 60:
        # BlueStacks launcher: bright search field on a dark background — the
        # game crashed or was closed. Without this, a crash looked like a
        # never-ending LOADING screen.
        return 'LAUNCHER'
    if dark < 45 and header < 45:
        return 'LOADING'
    if pause < 55:
        return 'BATTLE'
    if card > 160:   # victory ~232, defeat ~183, prep arena ~82
        title = v.avg(img, (960, 60))
        return 'DEFEAT' if title[2] > title[0] + 40 else 'RESULT'
    # the AFK panel has the same green Battle button as the prep screen; its
    # orange "Claim" chip at (1390,704) is the reliable difference
    # "Turn off Auto Battle?" / exit confirmations: bright round X at (1014,710)
    # and a green round check at (1155,710). Never confirm — cancel instead.
    xbtn = v.avg(img, (1014, 710))
    okbtn = v.avg(img, (1155, 710))
    if v.lum(xbtn) > 200 and okbtn[1] > okbtn[0] + 30 and okbtn[1] > 90:
        return 'CONFIRM'
    back = v.lum(v.avg(img, v.BACK))
    if back > 150 and v.lum(v.avg(img, (549, 846))) < 110 and v.lum(v.avg(img, (780, 1000))) < 120:
        return 'STATS'
    # dimmed reward/event popups and the dark 'Auto Battle Complete' summary
    # card: v.classify says POPUP, every heuristic above misreads the dimmed
    # frame — report it instead of tapping blind (handlers OCR-check it)
    if v.classify(img) == 'POPUP':
        return 'POPUP'
    if v.avg(img, BATTLE_BTN)[1] > 150:
        return 'PREP'
    return 'UNKNOWN'


# --- T41: wall report (OCR on the real screen, offline WinRT OCR) -------------

def ocr_text(png: Path) -> list[str]:
    """Run templates/ocr.ps1 (Windows.Media.Ocr) on a screenshot PNG."""
    png = Path(png).resolve()          # ocr.ps1 needs absolute native paths
    try:
        p = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(OCR_PS1), "-Path", str(png)],
            capture_output=True, timeout=90, text=True, encoding="utf-8",
            errors="replace")
        if p.returncode != 0:
            return []
        return [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    except (subprocess.SubprocessError, OSError):
        return []


def parse_stage(lines: list[str]) -> int | None:
    """Stage number from OCR lines like 'AFK Stage 249' / 'AFK 249'."""
    for ln in lines:
        m = re.search(r"AFK\s*(?:Stage\s*)?(\d{1,4})", ln, re.I)
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
    wins over the team power higher up.
    """
    for i, ln in enumerate(lines):
        if re.fullmatch(r"Battle", ln.strip(), re.I):
            for j in reversed(range(i - 8, i + 2)):
                if 0 <= j < len(lines) and j != i:
                    for m in re.finditer(r"(\d{1,3}(?:[.,]\d{3})+|\d{4,8})", lines[j]):
                        val = int(m.group(1).replace(",", "").replace(".", ""))
                        if 5_000 <= val <= 5_000_000:
                            return val
    return None


def is_auto_complete(lines: list[str]) -> bool:
    """The auto chain's end card ('Auto Battle Complete' / 'Tap to Close')."""
    joined = " ".join(lines).lower()
    return "auto battle complete" in joined


def wall_report(reason: str, tag: str = "sp_wall_report") -> dict:
    """Screenshot -> OCR -> JSONL line in .spectre/wall-report.log.

    Never raises: a failed report must not break the push run.
    """
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "reason": reason, "stage": None, "power": None}
    try:
        img = v.shot(tag)
        png = v.TMP / f"{tag}.png"
        lines = ocr_text(png)
        rec["stage"] = parse_stage(lines)
        rec["power"] = parse_power(lines)
        rec["lines"] = lines[:14]
    except Exception as exc:                      # noqa: BLE001 - report must not kill the run
        rec["error"] = f"{type(exc).__name__}: {exc}"
    try:
        WALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(WALL_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as exc:
        rec["error"] = f"log write failed: {exc}"
    print(f"    wall report: {reason} stage={rec.get('stage')} "
          f"power={rec.get('power')}", flush=True)
    return rec


def wait_for(states: set[str], timeout: float, tag: str) -> tuple[str, object]:
    t0 = time.time()
    last = 'UNKNOWN'
    while time.time() - t0 < timeout:
        img = v.shot(tag)
        last = classify_battle(img)
        if last == 'STATS':
            v.tap(v.BACK, 1.5)
        elif last == 'CONFIRM':
            v.tap((1014, 710), 1.5)   # cancel, never confirm
        if last in states:
            return last, img
        if last == 'LAUNCHER':          # game crashed/closed: no point waiting
            return last, img
        time.sleep(2.0)
    return last, None


def main() -> int:
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
        if status == 'stale':
            print(f'    WARN: team_power offset stale after restart (read {power})', flush=True)
        else:
            print(f'    preflight team_power = {power}', flush=True)

    img = v.shot('sp_0_initial')
    st = classify_battle(img)
    print(f'    initial battle screen state: {st}', flush=True)

    if st in ('UNKNOWN', 'POPUP'):
        if is_auto_complete(ocr_text(v.TMP / 'sp_0_initial.png')):
            print('    auto battle summary card open — closing it', flush=True)
            v.tap((960, 1000), 2.5)   # 'Tap to Close' sits bottom-centre
            img = v.shot('sp_after_close')
            st = classify_battle(img)
            print(f'    after closing summary: {st}', flush=True)
        if st == 'UNKNOWN':
            print('    ERROR: unknown screen — refusing to tap blind', flush=True)
            return 1
    if st == 'POPUP':
        # a reward/event popup blocks the flow; cancelling blind risks a buy
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
                v.tap((1014, 710), 2.0)         # cancel, never confirm
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
            st = classify_battle(v.shot('sp_auto_start_recheck'))
            if st == 'BATTLE':
                print('    auto battle started (confirmed on recheck)', flush=True)
        if st in ('PREP', 'RESULT', 'DEFEAT'):
            # Auto Battle is inert after a defeat: fall through to single battles
            # instead of idling until the timeout.
            print('    auto battle not available — fighting single battles', flush=True)
            args.auto = False
            if args.battles < 3:
                args.battles = 3
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
            while time.time() - t0 < args.auto_minutes * 60:
                time.sleep(3)
                tag = f'sp_auto_{int(time.time()-t0)}'
                img = v.shot(tag)
                st = classify_battle(img)
                if st in ('UNKNOWN', 'POPUP') and is_auto_complete(ocr_text(v.TMP / f'{tag}.png')):
                    # the chain ended by itself: close the summary card and
                    # restart Auto Battle while the time window is open
                    print('    auto battle complete — closing summary, restarting', flush=True)
                    v.tap((960, 1000), 2.5)   # 'Tap to Close' sits bottom-centre
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
                if st == 'BATTLE':
                    v.tap(SKIP_BTN, 1.5)   # resolve the fight instantly
                    skipped += 1
                elif st == 'CONFIRM':
                    v.tap((1014, 710), 1.5)   # cancel "turn off auto battle?"
                elif st == 'STATS':
                    v.tap(v.BACK, 1.5)
                elif st == 'DEFEAT':
                    wall_report(f'auto_defeat_after_{int(time.time()-t0)}s')
                    if args.retry_defeats:
                        print(f'    DEFEAT after {int(time.time()-t0)}s ({skipped} skipped) '
                              '- retrying (night mode)', flush=True)
                        v.tap((1280, 1020), 3.0)   # Retry button
                        continue
                    print(f'    DEFEAT after {int(time.time()-t0)}s ({skipped} skipped) '
                          '— stage wall reached', flush=True)
                    break
                elif st == 'PREP':
                    # debounce: a transient prep between chained fights looks
                    # like the wall, but the chain may already be losing —
                    # confirm with a second shot before reporting.
                    time.sleep(3)
                    st2 = classify_battle(v.shot('sp_auto_confirm'))
                    if st2 == 'DEFEAT':
                        wall_report(f'auto_defeat_after_{int(time.time()-t0)}s')
                        if args.retry_defeats:
                            print('    DEFEAT confirmed - retrying (night mode)', flush=True)
                            v.tap((1280, 1020), 3.0)   # Retry button
                            stable = 0
                            continue
                        print(f'    DEFEAT after {int(time.time()-t0)}s ({skipped} skipped) '
                              '— stage wall reached', flush=True)
                        break
                    wall_report(f'auto_prep_stop_{skipped}skipped_{int(time.time()-t0)}s')
                    print(f'    wall reached: {skipped} fights skipped in {int(time.time()-t0)}s',
                          flush=True)
                    break
            else:
                # leave the game clean: cancel a possibly open confirm dialog
                # (a stray skip tap can hit the auto toggle) and close the
                # auto-complete summary card, THEN report the resulting state.
                img = v.shot('sp_auto_end')
                end_st = classify_battle(img)
                if end_st == 'CONFIRM':
                    v.tap((1014, 710), 2.0)
                    end_st = classify_battle(v.shot('sp_auto_end2'))
                elif end_st in ('UNKNOWN', 'POPUP') and is_auto_complete(ocr_text(v.TMP / 'sp_auto_end.png')):
                    v.tap((960, 1000), 2.5)
                    end_st = classify_battle(v.shot('sp_auto_end2'))
                wall_report(f'auto_timeout_{skipped}skipped_end_{end_st.lower()}')
                print(f'    still fighting after {args.auto_minutes:.0f} min ({skipped} skipped)',
                      flush=True)
            return 0

    for i in range(1, args.battles + 1):
        v.tap(BATTLE_BTN, 3.0)
        st, _ = wait_for({'BATTLE', 'RESULT'}, 25, f'sp_start_{i}')
        print(f'    battle {i}: started ({st})', flush=True)
        if st == 'BATTLE':
            st, _ = wait_for({'RESULT', 'PREP'}, args.max_battle_seconds, f'sp_end_{i}')
        if st == 'RESULT':
            wins += 1
            print(f'    battle {i}: VICTORY (AFK progress +1)', flush=True)
        else:
            # neither result card nor prep after a battle: likely defeat or stall
            wall_report(f'battle_{i}_no_victory_{st.lower()}')
            print(f'    battle {i}: no victory screen ({st}) — likely DEFEAT, stopping', flush=True)
            break
        time.sleep(1.5)

    if wins:
        wall_report(f'single_push_complete_{wins}of{args.battles}')
    print(f'    pushed {wins}/{args.battles} stage(s); game left on the result screen', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
