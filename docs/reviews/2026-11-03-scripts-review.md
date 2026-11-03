All evidence gathered. Composing the final structured report.

```json
{
  "summary": "Reviewed the six target scripts by full read plus live verification: imported the actual modules, re-ran their detectors/functions against 40+ real screenshots in .spectre (arena dialog frames, gift/quest/chest flows), ran the wall-report parser against crafted garbage/null/string inputs, ran the OCR parser battery on real OCR output, and checked the live device (adb reachable). Headline verified problems: (1) afk_arena.confirm_dialog probes sit ~50px below the real purchase-dialog buttons, so the never-spend-diamonds gate never fires (proved on the only real dialog captures where the stage_push variant, using different y, does fire); (2) afk_hero_level's level parser truncates/glues numbers (\"Lv.74986\" -> 749, \"LvL99\"/\"LV.74\" -> None) and its key(4) bail-outs can exit the Resonating Hall with no way back; (3) afk-wall-dash crashes (uncaught) on any non-dict/None JSONL entry, on a string power, or on a null power in state, and its Walls/Progress counters never match the producer's reason strings; (4) afk_arena returns exit code 0 on both abort paths, so afk-bot-watch.sh burns the once-per-day arena marker on failed runs; (5) claim_vision.classify has a real 1-luminance-point-wide POPUP-vs-WORLD boundary (a live arena frame reads d=-9 against the -8 threshold), risking exactly the blind-tap-into-popup failure the module exists to prevent; (6) .spectre has grown to 1.3 GB across 104 unpruned shots-* dirs. Note: afk_arena.py was edited during review (mtime 2026-11-03 01:32, md5 3bdf68cb...); all findings refer to that current revision. afk_claim_vision.context: the 10-31 log also shows a historical SyntaxError from an intermediate revision (fixed).",
  "findings": [
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L106-113 (probes L111-112), tap L189",
      "severity": "HIGH",
      "why": "confirm_dialog is meant to detect the 'Spend <diamonds> to purchase...' dialog (must always be cancelled, never confirmed), but its probes avg((1014,784)) and avg((1140,784)) sit ~50px below the real button row. Pixel-blob analysis of the ground-truth dialog frame (screens/arena_debug1.png, pixel-identical probes to shots/arena_2_select.png and arena_f1_step0..5 -- i.e. the dialog was actually up in a real capture) puts the white X circle at ~(1010,728) and the green check at ~(1142,734); at y=784 both probes land on empty backdrop: (1014,784) averages (108,116,123) -> sum/3=116 fails '>180', (1140,784) (64,84,61) fails 'green'. Result: confirm_dialog() returned False on every real dialog frame available, the advance_to_fight loop burned all 6 steps tapping the dialog (steps 0..5 probe-identical) and returned STUCK, and even the cancel tap at (1014,784) lands below the X button.",
      "fix": "Move probes onto the buttons (e.g. X avg((1012,730)) bright, check avg((1142,732)) green) -- or better, reuse the already-correct stage_push CONFIRM coordinates (1014,710)/(1155,710), which evaluate True on the same frame -- and move the cancel tap to ~(1010,728). Unify one purchase-dialog detector in afk_claim_vision and import it in both afk_arena and afk_stage_push."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_hero_level.py",
      "line": "L73-79 (read_level), L82-83 (is_detail), key(4) L101/106/112/116/127/130",
      "severity": "HIGH",
      "why": "read_level regex r'Lv[l.\\s]*\\.?\\s*(\\d{1,3})' is unanchored and truncation-prone. Verified on real strings: 'Lv.74986' -> 749, 'Lv. 1234' -> 123 (both wrong; a wrong 749 also reads as >= target so the hand is skipped as 'done'), while common OCR forms 'LvL99' and 'LV.74' return None. Separately, is_detail() accepts any line containing 'Level', so the hall ('Resonance Level: 80') passes as a detail while read_level(hall) is None -> the code prints 'level unreadable - skip', calls key(4), and key(4) then EXITS the hall. The next hand taps (x,460) into the town with no re-navigation; hl_710_0.png even OCR'd empty on attempt 0 (needed the _0b retry taken at L96-98), showing how easily a hand's first tap/read fails. The run still exits 0 ('done') even if every hand failed.",
      "fix": "Parse case-insensitively with a glued-run guard and a plausibility range, e.g. m=re.search(r'(?i)\\blv[l.\\s]*\\.?\\s*(\\d{1,6})', ln); n=int(m.group(1)); if n>300: n=int(m.group(1)[:2]) if int(m.group(1)[:2])>=10 else int(m.group(1)[:3]); validate 1..300. Tighten is_detail (require 'Lv' badge or 'Ascend'+'Level Up' together). After every key(4), re-OCR and if not in hall, re-tap (972,1034); return exit code 1 if any hand was unreadable/not found."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-wall-dash.py",
      "line": "L27-31 (load), L53",
      "severity": "HIGH",
      "why": "garbage/non-dict JSONL robustness is broken: any line that parses as JSON but is not a dict ('null', '123', '[1,2,3]') is appended and later dies with AttributeError: 'NoneType'/'int'/'list' object has no attribute 'get' -- proven by running main() against crafted logs; a single such line kills the whole widget. Same for the state file: STATE content '[1,2]' -> AttributeError on cur.get. json.loads succeeds for these, so the except-continue never helps.",
      "fix": "In load(): obj=json.loads(line); if isinstance(obj, dict): evs.append(obj). Guard the state: if not isinstance(cur, dict): cur={}. Optionally drop non-dict entries at render time too."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-wall-dash.py",
      "line": "L59, L73-74",
      "severity": "HIGH",
      "why": "Value formatting crashes on plausible inputs, each proven by execution: power as string -> ValueError \"Cannot specify ',' with 's'\" at '{:,}'.format(e['power']); power null in state -> TypeError at f\"{cur.get('power', 0):,}\" (key exists, value None). Producer (afk_stage_push.wall_report) writes \"stage\": null, \"power\": null on many events today, so any future string value or state.json with a null power takes the dashboard down.",
      "fix": "Add one coercion helper: def fmt_int(v): try: return f'{int(v):,}' except (TypeError, ValueError): return '—' and use it for both the row power cell and the state power tile."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L193-195, L202-204, L208",
      "severity": "HIGH",
      "why": "Both failure exits use break and then fall through to return 0, contradicting the module docstring ('1 = stuck / unknown'). afk-bot-watch.sh (L171-181) writes the once-per-day arena-last.txt marker only when the first attempt exits 0, so a run that never reached a fight (e.g. the broken dialog detection above, or a STUCK advance) silently burns the day's arena attempts.",
      "fix": "Track an ok flag; on advance STUCK or 'screen unchanged' return 1 (or at least return 1 when wins==0 and st!='PREP'); make watch.sh set first_ok on any attempt with rc==0."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_claim_vision.py",
      "line": "L302-312 (open_battle_modes), L286-289 (is_battle_modes)",
      "severity": "MED",
      "why": "is_battle_modes (body L>200 at (480,270) AND tabbar L>200 at (890,934)) false-positives on bright daytime world frames: verified is_battle_modes(shots/arena_0_initial.png)=True with probes 232/245 while that frame is the world. open_battle_modes checks the probe BEFORE any tap, so on such frames it returns True without ever opening the menu, and afk_arena then taps ARENA_CARD (1200,300) blindly in the world -> 'arena lobby did not open'. The world HUD has distinguishing elements (e.g. the AFK chip at (60,1036), used by stage_push as a WORLD gate) that the probe ignores.",
      "fix": "Exclude the world: require is_battle_modes AND lum(avg(img,(60,1036)))<100 (or classify(img)!='WORLD' with the chip present), or verify two probes specific to the menu and tap BATTLE_MODES at least once before accepting."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_claim_vision.py",
      "line": "L353-356 (classify POPUP/WORLD boundary)",
      "severity": "MED",
      "why": "The POPUP-vs-WORLD split is a 1-luminance-point cliff: POPUP needs lb<100 and (lbar>172 or lb-lg<-8); WORLD needs lb<100 and |lb-lg|<8. Synthetic frames show a dimmed popup without a bright claim bar and d in (-8,0) classifies WORLD; real frame shots/arena_0_final.png sits at d=-9 (one point from the wrong verdict; it is only saved by its bright lbar). A WORLD verdict makes main() tap GROUND+AFK_PROGRESS into a live popup -- the exact failure the module exists to prevent.",
      "fix": "Add a third tell-tale instead of tuning the cliff: e.g. a dim overlay darkens multiple points, so require for WORLD an additional world-only element (AFK chip >100, as stage_push does) and return UNKNOWN (refuse taps) when dark-back-arrow frames disagree -- UNKNOWN already aborts safely."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_dailies.py",
      "line": "L92 (ARGS use), L200-207, L204-205",
      "severity": "MED",
      "why": "run_dailies() reads the module global ARGS, which is only set inside the __main__ block; importing the module and calling run_dailies() raises AttributeError: 'NoneType' object has no attribute 'pid' at L92. Also --pid/--base are required=True while L92-99 handles their absence ('skip' branch is dead), and L102-103's 'WARN: team_power offset stale' else-branch is unreachable (memory_preflight only returns ok/disabled/fail).",
      "fix": "Make run_dailies take args explicitly (or set a default ARGS = argparse.Namespace(pid=None, base=None, min_idle=0)); drop required=True or the dead branch."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_dailies.py",
      "line": "L55-68 + callers L124-132",
      "severity": "MED",
      "why": "quick_claim_tab failures are swallowed and the caller keeps tapping the next tab coordinate on whatever screen is current -- no classify/re-verify between tabs, contradicting the module's 'every tap is gated' promise. A stale panel (is_quests_panel true on the previous tab) also passes the gate, so a failed tab switch results in a QUICK_CLAIM tap on the wrong tab (double claim / missed claim). Probe fragility is real: open_menu's 2-probe check failed live on 10-31 18:44 ('ERROR: main menu did not open' after 3 attempts).",
      "fix": "Return the post-shot from quick_claim_tab; on any failure tap BACK and re-open the quest panel before the next tab; in open_menu, on failure fall back to classify(img) checks / extra retries instead of aborting."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-daily-gift.py",
      "line": "L133-137, L127-132, L62-65, L68-79",
      "severity": "MED",
      "why": "The entry-to-panel chain failed live: log 10-31 15:24 shows 'ERROR: Login Rewards panel did not open', and .spectre/shots/dg_panel.png (the shot taken right after tapping the entry) is a plain world frame -- i.e. find_login_button reported visible but the tap opened nothing. login_btn_visible (red>200, blue<120, r-b>80 at a fixed (1804,662)) can false-positive on world elements, and the 'no entry' fallback returns 0, which (via watch.sh) writes daily-gift-last.txt and marks the day done -- masking the failure. is_events_panel itself is camera-marginal: True on dg_row_260.png but the panel's own post-tap frames can read as world.",
      "fix": "After tap(LOGIN_REWARDS), retry the is_events_panel check 2-3 times (open animation), and retry the tap once before erroring; make the not-found path return a distinct code or log WARN; verify the entry probe against a second pixel (e.g. bubble outline) before tapping."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-daily-gift.py",
      "line": "L45-46, L153-164",
      "severity": "MED",
      "why": "is_dimmed uses a single probe (200,270) with threshold <25 for the 'Rewards Obtained' success popup, but no captured shot ever exercised this branch true (logs only show 'nothing claimable'/'item info'; dg_after_260.png after a green-badge row read is_dimmed=False and was classified as tooltip). Adjacent real states sit at lum 59-60 (panel/other), dimmed chest popup at 17 -- a 25 threshold leaves only ~8 points of margin if any 'Rewards Obtained' variant dims differently, and a miss here means a claimed day is logged as claimed-nothing (break+dismiss never run).",
      "fix": "Detect success as (is_dimmed(img) or v.classify(img)=='POPUP') with a re-shot after the tap; keep the 25 floor but add the classify fallback and log which signal fired."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_hero_level.py",
      "line": "L119-129",
      "severity": "MED",
      "why": "'resources exhausted' is inferred from a single unchanged level re-read after the x10 tap and then stops the ENTIRE run (stop_flag). A missed/short tap (adb hiccup, tap during animation) also yields an unchanged level, so one flaky tap aborts all remaining hands and the run reports 'resources exhausted' wrongly; there is no retry/confirmation of the stop condition (the docstring's 'x10 button disabled' is never actually probed).",
      "fix": "On unchanged level, tap x10 once more and re-read; only set stop_flag when two consecutive taps change nothing. Optionally probe the x10 button's greyed colour before tapping."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_hero_level.py",
      "line": "L108-113, L130-131",
      "severity": "MED",
      "why": "level_hand returns `lvl`, which is only assigned at attempt 0; when the x10 cap is reached (the normal case for a hand leveled by 2 taps, e.g. 74 -> 94) the function returns the STALE attempt-0 level, so 'final level' prints and the 'lowest hand after run' min() are wrong (conservative but misleading). Additionally the whole script has no screen-state gating between hands: after each key(4) the next hand tap assumes the hall.",
      "fix": "Track last_level on every read and return it; before each hand's tap, OCR-verify the hall ('Resonance Level' present) and re-enter via (972,1034) if missing; classify-gate the x10 tap (require a detail screen)."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_hero_level.py",
      "line": "L142-147 (entry), L44-58 (shot)",
      "severity": "MED",
      "why": "The script navigates by one blind bottom-nav tap and a single OCR text check with no state classification or recovery, unlike the other drivers; a sub-panel or a failed nav tap just aborts. shot() also ignores the screencap returncode, so a failed screencap yields an empty/partial PNG whose OCR is [] -- indistinguishable from 'not a detail', again ending in key(4) state drift. This file also duplicates the whole ADB/tap/shot/OCR stack (third OCR copy across scripts, hardcoded C:/Users/Sigi paths vs Path.home() elsewhere), so fixes drift between copies (its regex already differs from _level_hands.py's).",
      "fix": "Extract a shared module (e.g. afk_common.py: adb/tap/shot/ocr_text + classify) and import it here; make shot() check returncode and rename-bad frames; add keyevent-BACK + bottom-nav retry loop for the entry."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_dailies.py",
      "line": "L159-197",
      "severity": "MED",
      "why": "afk_chest_claim re-implements afk_claim_vision.main's chest sequence instead of sharing it, and has already diverged: different retry counts, returns True even when the claim state is unexpected (prints 'state POPUP' but lets the run continue), and no claim-retry step; claim_vision returns 1 in that case. Two copies of the same live-verified tap flow will keep diverging.",
      "fix": "Move the chest-claim flow into afk_claim_vision as a function and call it from both mains; keep return semantics (bool) consistent."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_claim_vision.py",
      "line": "L35, L252-266",
      "severity": "MED",
      "why": "Every run writes screenshots into a per-pid shots-{pid}/ dir and nothing ever prunes them: .spectre currently holds 104 shots-* dirs and 1.3 GB (single dir up to 73 MB). Long-term scheduled operation grows disk unbounded. idle_seconds (L315-335) also has a real edge: ctypes default restype for GetTickCount is c_long (verified: restype <class 'ctypes.c_long'>), so after ~24.8 days of Windows uptime the tick goes negative and (GetTickCount()-dwTime) becomes a large negative number -> idle<min_idle -> every scheduled run SKIPs as 'PC in use' until reboot.",
      "fix": "Prune shots-* dirs older than N days (or keep last K) at startup; in idle_seconds set GetTickCount.restype = ctypes.c_uint32 and compute (tick - lii.dwTime) & 0xFFFFFFFF (or use GetTickCount64 with matching mask for dwTime)."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-wall-dash.py",
      "line": "L54-55",
      "severity": "MED",
      "why": "The dashboard stats never work on real data: defeated counts reason=='defeat' and progress counts reason=='progress', but the producer writes reasons like 'wall_defeat_initial', 'auto_defeat_after_20s', 'auto_timeout_17skipped', 'battle_1_no_victory_prep' -- exact equality matches nothing (verified against the real wall-report.log: both counters render 0 despite 5+ defeat events).",
      "fix": "Classify by family, e.g. 'defeat' in reason -> walls, 'progress'/'victory'/'cleared' in reason -> progress, and document the expected reason vocabulary next to the producer."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-wall-dash.py",
      "line": "L58, L39-43, L13, L51",
      "severity": "MED",
      "why": "Assorted display/provenance bugs: stage null renders the literal string 'None' (esc(e.get('stage','—')) returns None, str() -> 'None') for almost every real event (producer emits \"stage\": null); human_ts expects a numeric ts but the producer writes ISO strings, so the fromtimestamp branch is dead and the Time column shows raw ISO; STATE points at .spectre/afk-state.json which NOTHING writes (repo-wide grep: only this file references it, file absent) so the Stage/Power tiles are permanently 0/0; 'last = evs[-1]' (L53) is never used.",
      "fix": "stage: use `e.get('stage') if e.get('stage') is not None else '—'`. ts: parse ISO via datetime.fromisoformat when ts is a string, fall back to the raw string. Drop STATE or derive current stage/power from the last event that has them. Remove the dead `last`."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L62-64",
      "severity": "MED",
      "why": "arena.tap ignores the adb returncode while afk_claim_vision.tap raises RuntimeError on failure -- a divergence that hides silently missed taps (e.g. the Challenge tap no-op leads to a STUCK advance loop and, per the exit-code bug, a 'successful' run).",
      "fix": "Mirror v.tap: raise on rc != 0 (or import v.tap). Also consider retry-once semantics."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_hero_level.py",
      "line": "L119-131 (x10 area), L86-107",
      "severity": "MED",
      "why": "Blind-tap-into-purchase-dialog surface: the policy is 'gold/EXP/essence only, never diamonds', but if the game raises an 'insufficient EXP, use diamonds?' confirm after an x10 tap, the script has no dialog detection: the popup's OCR typically lacks 'Lv' -> lvl2 None -> 'level unreadable - skip' -> key(4) (which may close only the popup, leaving the detail open) and the next hand tap lands on the wrong screen. No capture proves or disproves the dialog exists; the branch is untested.",
      "fix": "After an x10 tap, if the new frame is not a detail (or lvl2 None), take a second shot after 1s; on a dimmed/popup-looking frame tap BACK once, re-OCR the detail and continue there instead of bailing to the next hand."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L36 vs L55",
      "severity": "LOW",
      "why": "'import afk_claim_vision as v' happens BEFORE sys.path.insert(0, scripts) (L55); it only works because running the file directly puts its own dir on sys.path. `python -m scripts.afk_arena` from the repo root would ModuleNotFoundError.",
      "fix": "Move the sys.path.insert above the afk_claim_vision imports (as afk_dailies.py and afk-daily-gift.py already do)."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L87-102, L37",
      "severity": "LOW",
      "why": "reach_world()/at_world() are dead code (main uses v.open_battle_modes, which has its own reach_world); 'from afk_claim_vision import classify' rebinds the same symbol as v.classify (double import). Docstring also claims classification 'via afk_stage_push.classify_battle' which is never called.",
      "fix": "Delete reach_world/at_world (or call it instead of the duplicated one), drop the redundant import, fix the docstring."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L67-74",
      "severity": "LOW",
      "why": "shot() returns Image.open(path).convert('RGB') without closing the source image (v.shot was fixed to close in a try/finally after a real fd-leak report); on the error path (convert raising) the handle stays referenced by the traceback.",
      "fix": "Import/copy the v.shot implementation (try/finally close) or simply use v.shot with a per-name path."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L166-171",
      "severity": "LOW",
      "why": "--dry-run is not actually dry: open_battle_modes() performs real BACK/GROUND/BATTLE_MODES taps before returning. Same pattern in afk_claim_vision.main (it taps to reach panels under --dry-run while skipping idle/preflight).",
      "fix": "Document it ('dry = no claim/fight, navigation still taps') or add --no-tap; avoid users assuming zero side effects."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_arena.py",
      "line": "L121-129",
      "severity": "LOW",
      "why": "arena_state mislabels the arena lobby as 'PREP' (verified: arena_state(arena_1_lobby.png)=='PREP' because the green Challenge button bleeds into the (960,1010) probe). If advance_to_fight ever runs from the lobby it would tap ARENA_BATTLE (960,1010) instead of CHALLENGE (1080,1004) -- usually harmless since Challenge spans ~640-1490 x, but semantically confused and untested.",
      "fix": "Probe distinct x for lobby vs prep (e.g. check (1080,1004) green first as SELECT-lobby), or gate on the lobby predicate before entering the fight loop."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_claim_vision.py",
      "line": "L69-76, L247-249, L61-66",
      "severity": "LOW",
      "why": "adb_exec_dump lets subprocess.TimeoutExpired propagate (uncaught crash on a hung spectre dump despite the 300s timeout); swipe() ignores the adb returncode (tap raises, swipe doesn't -- inconsistent); save_power_state does a non-atomic write (write_text) so two unsynchronized invocations can clobber power-state.json (watch.sh serializes the scheduled path, manual runs don't).",
      "fix": "Wrap dump in try/except TimeoutExpired -> None; raise or return rc in swipe; write state via tmp file + os.replace."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_claim_vision.py",
      "line": "L409-424",
      "severity": "LOW",
      "why": "After a POPUP recovery the code can still be non-PANEL and then fires BACK,BACK,GROUND,AFK_PROGRESS blindly (e.g. closing a popup lands on a store/event screen -> BACK twice may punch through two layers); no classify between the two BACK taps.",
      "fix": "Classify between taps (BACK -> shot -> if still not WORLD/attempt) or reuse reach_world() before the AFK tap."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_dailies.py",
      "line": "L26, L39-41, L102-103",
      "severity": "LOW",
      "why": "Module TMP is unused (all shots go through v.shot); dismiss_popup() taps the fixed (480,300) blindly (functionally fine when the popup is up, unverified when it is not); the 'WARN: team_power offset stale' else-branch is dead as noted above.",
      "fix": "Delete TMP; make dismiss_popup verify is_dimmed after the tap and retry once; clean up the status branch table."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-daily-gift.py",
      "line": "L76-78, L97, L70-71",
      "severity": "LOW",
      "why": "Pan swipes compute x2 = 400-dx with dx up to 1300 -> x2 = -300/-900, i.e. off-screen destinations (adb accepted them in a live test, rc=0, but whether the touch registers off-screen is unverified); 'import struct' inside main() is unused; the pan always starts at (400,700), whose 'open grass, never a building' claim is camera-dependent.",
      "fix": "Clamp swipe endpoints into [0,1919]/[0,1079] (e.g. use shorter strokes or split into two), drop the stray import, and choose the swipe origin from a safe probe or document it."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk-daily-gift.py",
      "line": "L113, L119, L145, L160-170",
      "severity": "LOW",
      "why": "Several blind fixed-point dismiss taps: (700,500) x2 when a reward popup layer is detected, (1500,600) for tooltips, and after a claimed row. If an unexpected dialog sits under these points (e.g. an event/store confirm), the tap may hit a button rather than dismiss -- the module's purchase-risk areas are the event tabs it repeatedly taps.",
      "fix": "Before dismiss taps, classify: only tap (700,500) if is_dimmed, only tap (1500,600) if is_events_tooltip; otherwise fall back to BACK and re-verify with is_events_panel."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/afk_hero_level.py",
      "line": "L29, L40-70, L136-139",
      "severity": "LOW",
      "why": "SHOTDIR is shared across concurrent runs (fixed filenames hl_entry.png / hl_{x}_{attempt}.png -- collisions like the arena/dailies shots dirs, whereas claim_vision already moved to per-pid dirs for exactly this reason); --target parsing silently ignores a dangling '--target'; absolute C:/Users/Sigi paths duplicate claim_vision's Path.home() form.",
      "fix": "Use a per-pid shot dir (or reuse v.TMP), switch to argparse, and derive paths from Path.home()/REPO."
    },
    {
      "file": "C:/Users/Sigi/spectre/scripts/_level_hands.py",
      "line": "L46, L66-71",
      "severity": "LOW",
      "why": "Third copy of the ADB/tap/shot/OCR stack, and already diverged from afk_hero_level.py: it taps the hand row at y=500 while afk_hero_level taps y=460 for the same row, and its read_level regex (r'Lv[.\\s]*l?\\.?\\s*(\\d{1,3})') differs (both fail 'LvL99'/'LV.74', both truncate glued runs). Whichever y/regex is right, the copies disagree, and fix'ing one will not fix the other.",
      "fix": "Consolidate on the shared helper module + one read_level; re-verify the row y once (both samples were captured at different cameras, so pick the current top-of-row coordinate and document it)."
    }
  ],
  "files_reviewed": [
    "C:/Users/Sigi/spectre/scripts/afk_claim_vision.py",
    "C:/Users/Sigi/spectre/scripts/afk_dailies.py",
    "C:/Users/Sigi/spectre/scripts/afk_arena.py",
    "C:/Users/Sigi/spectre/scripts/afk_hero_level.py",
    "C:/Users/Sigi/spectre/scripts/afk-daily-gift.py",
    "C:/Users/Sigi/spectre/scripts/afk-wall-dash.py",
    "C:/Users/Sigi/spectre/scripts/_level_hands.py",
    "C:/Users/Sigi/spectre/scripts/afk-bot-watch.sh (call-site context)",
    "C:/Users/Sigi/spectre/scripts/afk_stage_push.py (wall-report producer / CONFIRM cross-check, context)"
  ]
}
```