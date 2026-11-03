# Review: afk_stage_push.py + afk_dream_realm.py (2026-11-03)

> Subagent-Review (unabhängig, artefakt-verifiziert gegen ~250 archivierte Frames
> in `.spectre/shots-*`, wall-report.log, git history; BlueStacks war offline,
> daher Artefakt-Ebene statt Live-Re-Run). Zeilennummern beziehen sich auf den
> committeten Stand (HEAD b52f869). Fund Nr. → direkt als A8 im Wave-2-Plan.
>
> **Headline:** Live-reproduzierbarer Fight-Start-Regress im Dream Realm —
> `start_fight` akzeptiert einen uniform-schwarzen Übergangs-Frame als „Kampf
> läuft"; in shots-33128 saß der Treiber dann 153 s auf dem Pre-Fight-Screen,
> lief in den Timeout und exitete 1 (Chance verbraucht, kein Resolve). Dazu:
> ~1,05 GB Screenshot-Leak, Classifier-Kreuzklassifikation (Live-Fight-Frames
> lesen LAUNCHER → „game crashed"), stale-RESULT-Phantom-Win, PREP-Debounce-
> Falschmeldung, ungeschützte v.shot-Aufrufe (adb-Hiccup = FATAL) u. a.

```json
{
  "summary": "Reviewed scripts/afk_stage_push.py and scripts/afk_dream_realm.py (HEAD, clean tree) plus the shared helper afk_claim_vision.py, cross-checked against git history, .spectre/wall-report.log, afk-bot-watch.sh and ~250 archived screenshots (probe re-measurement + vision ground truth). BlueStacks was off, so verification is artifact-level, not a live re-run. Headline: a live-reproducible fight-start regression in afk_dream_realm — start_fight accepts a plain black transition frame as 'fight underway'; in .spectre/shots-33128 the driver then sat 153 s on the pre-fight screen, timed out and exited 1 (exit 1, chance spent, no resolve shots), while the earlier equivalent run (shots-1752) shows the same black-then-pre-fight pattern only 'working' because the game eventually produced the end card 116 s after the tap (chances 5/7 -> 4/7). wait_for_fight_end has no ready-screen re-arm, so nothing recovers that state. Also found: ~1.05 GB screenshot leak (104 shots-<pid> dirs; prune trims only the current dir and only in afk_stage_push, dream_realm never prunes at all), classifier cross-talk where live fight frames read LAUNCHER (-> 'game crashed', exit 3) or LOADING (unknown strike -> abort), a stale-RESULT phantom win in the single-battle loop, a PREP-debounce false 'wall reached', unguarded v.shot calls that turn adb hiccups into FATAL exits, and parser/close-coordinate gaps. Line numbers refer to the committed files.",
  "findings": [
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "315-335 (start_fight)",
      "severity": "HIGH",
      "why": "start_fight declares the fight 'under way' on a uniform-black transition frame: after the Battle tap the k-loop (L321-324) treats ANY frame whose class differs from the tapped ready class as 'the ready state was left', and the follow-up shot (L332-335) returns True unless it is prep/boss, so two uniform-black frames end start_fight while the game is still loading boss->pre-fight and nobody ever taps the pre-fight Battle button. Artifact proof: .spectre/shots-33128/dr_f1_after0_0.png == dr_f1_changed0.png == uniform (29,29,29); the 25 following poll frames are pixel-identical to a known pre-fight shot (mean abs channel diff 1.7-3.5/255 vs 53 for a real in-fight frame); wait_for_fight_end then times out and the run exits 1 (no resolve/exit shots, last file 03:34:30). The same pattern in .spectre/shots-1752 fight 2 shows the code was fighting blind: boss page Chances 5/7 -> 4/7 and a real 98.6%/1795K result card appeared only 116 s after the tap.",
      "fix": "Add a positive fight marker and never accept undecided frames: after the tap keep polling until (a) prep/boss appears again -> continue (re-tap), or (b) the frame matches the in-fight profile calibrated from .spectre/shots-1752/dr_f1_w*.png: (960,1040) neither white (lum>200) nor _green AND lum((1280,1010)) < 120 (fight reads ~(22,32,72)). Uniform/dark frames keep polling up to the existing attempt cap instead of returning True."
    },
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "255-271 (wait_for_fight_end)",
      "severity": "HIGH",
      "why": "wait_for_fight_end only polls for ended/hero/dim; it never re-checks is_ready and never re-arms. If the fight never started (visible pre-fight screen, see finding above) nothing taps Battle again, the whole --wait-fight window (150 s) is burned on a static screen and the function returns None -> run() returns 1. This is exactly what run shots-33128 did (153 s of pre-fight frames, no end card, exit 1) - a daily chance lost.",
      "fix": "Count consecutive is_ready frames; after >=3 with no fight marker seen, tap PREP_TAP/BOSS_TAP once (charge the dismiss budget, log it) and keep polling. Use the is_fight() marker above so 'fight not started yet' is detectable at all."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "69-73 (LAUNCHER) and 74-75 (LOADING)",
      "severity": "MED",
      "why": "The LAUNCHER branch runs before the pause-based BATTLE check and has no fight exclusion, so live fight frames can be reported as 'game crashed' (wait_for returns immediately; the auto loop does wall_report + exit 3). Measured: honest launcher frames read search(960,124)=242.5, header(960,40)=229.6, pause(549,846)=195.9-199.9 (.spectre/shots-13340/dl_afk_0.png, .spectre/shots-14672/rw_0.png) while fight frames read search 30-180, header 54-128, pause 0-46 - and three archived dream-realm fight frames (shots-1752/dr_f1_w0,w3,w7: search 120.6-180.1, dark 13.9-49.3) already classify as LAUNCHER today. Related dead zone: dark night fight frames can satisfy the LOADING gate (shots-30096/sp_auto_52: header 31.3, dark 31.9, pause 23.0 = live fight classified LOADING), which counts as an unknown strike in the auto loop (15 -> abort) and is missing from every wait_for state set.",
      "fix": "Tighten the launcher gate (search > 200 and/or pause > 150; both separate the archived samples) and/or move it after the BATTLE check. Treat LOADING as 'no information' in the auto loop (do not increment unknowns) and add LOADING to the single-loop wait sets."
    },
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "111-123 (_dim_probes)",
      "severity": "MED",
      "why": "_dim_probes also matches the dark battle/loading transitions, not only dim popups (docstring claims black loading frames read ~0). Artifacts: .spectre/shots-1752/dr_f1_resolve_0.png reads back=(1,4,15), bar=(1,4,18), corner=(25,72,156) -> lum(corner)~67 -> dim=True; same for shots-10264/dr_f1_w7.png and shots-32592/dr_f1_resolve_0.png. Consequences: wait_for_fight_end returns a fight-START transition as 'fight ended', resolve_end_states spends a dismiss tap on it, is_ready(final) is false and back_to_ready then sees the still-running fight as unknown frames.",
      "fix": "Keep uniform-dark frames out of the end-state set: in wait_for_fight_end require the second confirmation shot (as dim_confirmed does) or exclude frames with lum<40 everywhere; in resolve_end_states only dismiss when the debounce shot is also dim AND the frame is no uniform transition."
    },
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "246-250 (back_to_ready)",
      "severity": "MED",
      "why": "back_to_ready's docstring says unknown frames are waited out because 'a fight may be running', but the code gives up after 4 unknowns (4 x 3 s ~ 12 s). A running fight is unknown for EVERY predicate (all archived fight frames classify UNKNOWN) and lasts ~90 s, so any call landing mid-fight aborts within ~12 s ('could not reach the world view' / 'boss page not restorable').",
      "fix": "Raise the consecutive-unknown tolerance (e.g. 20) or, after ~3 unknowns, fall into end-state polling bounded by --wait-fight (reuse wait_for_fight_end) before giving up."
    },
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "417-418",
      "severity": "MED",
      "why": "The 2x-speed tap fires 1.5 s after start_fight returns, ungated and unverified: in shots-33128 it was pressed while the screen was still the black transition (very likely swallowed -> fight at 1x = double wall-clock), and on a pre-fight screen (1092,788) it can land on a roster card. b69fbc4 verified the coordinates on a live fight, not the timing.",
      "fix": "Gate the tap on the fight marker (fire on the first poll where is_fight is true; retry once a few seconds later), never on a black/dim frame."
    },
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "318 + 405-431",
      "severity": "MED",
      "why": "No chance bookkeeping: --fights 7 runs unconditionally and any dim/popup frame right after the tap is accepted as 'fight started' (L318), so with fewer remaining chances or a chance-purchase flow the run prints 'fight N: completed (chance consumed)' for fights that never ran. The boss page prints 'Chances: N/7' - nothing reads it, nothing stops cleanly on an empty pool.",
      "fix": "Require the fight marker after the tap before counting a fight; log the chance counter once per fight via the existing offline OCR (templates/ocr.ps1) and stop with a distinct message when the flow is not a real fight (persistent dim dialog -> BACK -> stop)."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "553-564 + 573-574 (prune_shots); afk_dream_realm: none",
      "severity": "MED",
      "why": "The screenshot leak is only half-fixed: prune_shots keeps the newest 30 PNGs inside the CURRENT per-PID dir (.spectre/shots-<pid>) and is called only from afk_stage_push's __main__; afk_dream_realm never prunes (7 fights ~ 300+ PNGs/run) and shots-<pid> dirs are never deleted. Measured now: 104 .spectre/shots-* dirs, 1.05 GB of PNGs, dirs holding 32-94 files; afk-bot-watch.sh runs both scripts daily.",
      "fix": "Move the prune into afk_claim_vision (shared): delete shots-* dirs whose PID is dead and older than ~1 day, enforce a global newest-N cap across all shots dirs, and call it from both __main__s plus periodically inside the long loops (dream_realm per fight)."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "522-535",
      "severity": "MED",
      "why": "A stale RESULT card counts as a victory: the loop taps BATTLE_BTN and treats an immediate 'RESULT' from wait_for as a win (`if st == 'RESULT': wins += 1`) although no battle phase was ever seen. If that tap is swallowed in a transition (the exact case the PREP branch re-taps for), the leftover card yields phantom wins up to --battles and exit 0 without a single fight.",
      "fix": "Require BATTLE/LOADING before a RESULT counts, or close/ignore a leftover result card before the first tap; handle an immediate RESULT like the PREP case (one re-tap, then report)."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "461-489",
      "severity": "MED",
      "why": "The PREP debounce breaks on ANY second frame that is not DEFEAT: if the chain simply re-armed within those 3 s (st2 == BATTLE/LOADING/RESULT) the loop prints 'wall reached: N fights skipped' and returns 0 while the chain is still running; the same break fires on a CONFIRM dialog or popup second frame.",
      "fix": "Break only when st2 is still PREP (take a third shot after another 3 s when ambiguous); continue for BATTLE/LOADING/RESULT (close + re-arm on RESULT as the RESULT branch does), cancel CONFIRM, then re-check."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "265, 360, 466, 503-510 (+390-394)",
      "severity": "MED",
      "why": "adb-failure handling is inconsistent: only the main poll is guarded; the initial shot, the auto-start recheck, the PREP debounce and the whole timeout epilogue raise to the top-level handler -> 'FATAL' + exit 1 mid-run, losing a minutes-long chain. In the auto loop the failure path `continue`s with no backoff (L390-394), so a fast-failing adb (device offline) spins hot for the whole window.",
      "fix": "One shared try_shot(name, tries=3, backoff=3s) for every v.shot call; count consecutive failures, abort with the adb exit code (2) after ~5 instead of a FATAL, and always sleep before retrying."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "400 + 490-498",
      "severity": "MED",
      "why": "The only mid-chain popup handled is the 'Auto Battle Complete' summary card (English-substring OCR); every other persistent popup (level-up/reward/hero popups are routine after fights) increments unknowns and aborts the chain at 15 polls (~50-90 s incl. per-poll OCR). Archived stall pattern: .spectre/shots-30096/sp_auto_111..180 = 22 identical POPUP frames (pause=94.4) of exactly that card until the run timed out.",
      "fix": "Add an OCR-gated fallback for the frequent cases (lines contain 'Level', 'Perk', 'Tap to close' -> tap (960,540), the victory-card close point), and on the strike threshold try one BACK + one centre-tap before aborting; reset the strike counter when OCR matched but the screen did not change."
    },
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "285-293 (reach_world)",
      "severity": "LOW",
      "why": "reach_world aborts on the first UNKNOWN frame although every predicate misses a running fight (fight frames are UNKNOWN), so starting the script while a fight runs prints 'could not reach the world view' and exits 1.",
      "fix": "On UNKNOWN at entry, poll a few frames (or delegate to wait_for_fight_end) before aborting."
    },
    {
      "file": "scripts/afk_dream_realm.py",
      "line": "99-108, 220, 166, 48",
      "severity": "LOW",
      "why": "is_hero_card margins are thin: HERO_PROBE (474,1010) already reads 171.2 on every archived boss-page frame (threshold 170, margin 1.2 lum) and only HERO_PROBE2 (133.3 vs 150) keeps a ready screen from being taken for a hero card - a theme change flips is_ready=False and back_to_ready taps (100,100) on a ready screen up to 8 rounds -> abort. Also: resolve_end_states returns None after round 8 without re-checking (a card closed on the last action still reports failure), REPO (L48) is unused, is_dim_popup duplicates _dim_probes, and the dismiss budget covers only resolve_end_states.",
      "fix": "Move HERO_PROBE off the shared back-arrow point or raise it to >=180 (the hero card is a full bright screen); re-classify after the 8th resolve action; count start_fight/back_to_ready taps in the global budget."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "91-92 vs 102-103; 41+44",
      "severity": "LOW",
      "why": "Duplicated/dead classifier logic: the second `v.classify(img) == 'POPUP'` check (102-103) is unreachable (91-92 already returned), and `dark`/`card` are the same probe (960,300) under two names, so the LAUNCHER gate (dark<60) and the RESULT/DEFEAT branch (card>160) silently share one point.",
      "fix": "Delete the dead POPUP check; give the result-card branch its own probe or document the shared point in both spots."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "272, 404, 509",
      "severity": "LOW",
      "why": "The summary/victory close at (960,1000) is the least-verified blind tap: on a real victory/summary screenshot the card's bottom edge is ~y960, so (960,1000) sits on the strip below the card where the pre-screen has its wide 'Auto Battle' pill (x ~660-1065, verified on .spectre/shots-49936/sp_prep.png), i.e. the tap can hit the Auto Battle toggle instead of the card; the archived timeout record 2026-11-01T01:27:37 ('Auto Battle Complete' in lines) classified 'unknown' right after that tap.",
      "fix": "Use the card centre (960,540) as the primary close (as the RESULT branch does), classify afterwards, and only then fall back to another point; keep the CONFIRM cancel for the toggle case."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "150-163 (parse_power)",
      "severity": "LOW",
      "why": "parse_power contradicts its docstring ('scan upward'): the loop checks j=i+1 (the line BELOW the anchor) first, so a number under 'Battle' beats the button's own power above; the anchor `fullmatch('Battle')` also misses OCR variants ('Battle !', 'Battle .'), silently logging power=None.",
      "fix": "Iterate upward first (range(i-1, i-9, -1)) then i+1; loosen the anchor to re.match(r'^Battle\\b', ln) while keeping the 'Auto Battle' exclusion."
    },
    {
      "file": "scripts/afk_stage_push.py",
      "line": "193-200 (wall_report)",
      "severity": "LOW",
      "why": "The second try/except overwrites rec['error'], so when the report body fails AND the log write fails the original reason is lost; the 15 s OCR timeout also covers the first cold WinRT/PowerShell init per process, so the initial auto-complete check can silently degrade.",
      "fix": "Keep the first error and add 'log_error' separately; raise the OCR timeout to ~30 s for the first call (or warm it up once)."
    }
  ],
  "files_reviewed": ["scripts/afk_stage_push.py", "scripts/afk_dream_realm.py", "scripts/afk_claim_vision.py"]
}
```

> Vollständiger Live-Transkript des Reviewers:
> `C:\Users\Sigi\AppData\Local\hermes\cache\delegation\live\deleg_6f05cc81\task-0.log`
