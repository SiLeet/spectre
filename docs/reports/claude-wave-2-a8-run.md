# Claude Wave-2 A8 Run — Abschlussbericht (2026-11-03)

Auftrag: A8a → A8b → A8c (Runtime-Review `docs/reviews/2026-11-03-runtime-review.md`),
1 Finding = 1 Commit, Branch `feature/T60-runtime-fixes`, offline.
Ergebnis: **alle 18 Findings FIXED, 18 Commits, nichts blockiert.**

`R<n>` = Position des Findings im JSON-Array des Runtime-Reviews.

## Git

- Branch `feature/T60-runtime-fixes` basiert auf `main` = `537b992` (unverändert seit
  Start) → **fast-forward-fähig**; `git merge-tree` gegen `main`: konfliktfrei.
- Gearbeitet im Worktree `C:\Users\Sigi\spectre-a8` — **ohne `.spectre`-Junction**
  (Lehre aus R13). Abbau gefahrlos: `git worktree remove ../spectre-a8`.
- `.spectre` wurde nicht angefasst (Kontrolle nach jedem Testlauf: nur `shots-4392`).

## Testausgabe (echt)

```
$ python -m unittest discover -s scripts/tests -v
frame regression: checked=0 skipped=139 manifest=139
...
Ran 147 tests in 2.492s

OK (skipped=22)
```

Baseline 107 → 147 (+40 in `scripts/tests/test_runtime_fixes.py`). Die 22 Skips sind die
Real-Frame-Tests aus Wave A (`.spectre` leer, R13) — erwartet.
Neue synthetische Frames in `fake_vision.py`: `DR_BOSS/PREP/FIGHT/BLACK/TRANSITION/DIM/ENDED`,
`SP_PREP/LOADING/BATTLE/RESULT/LAUNCHER` (Werte aus Report bzw. Modul-Docstrings).

## Items

| Item | Finding | Commit | Status / Kern |
|---|---|---|---|
| A8a-1 | R1 dream start_fight | `c76415b` | FIXED — `is_fight()`: (960,1040) weder weiß noch grün, lum(1280,1010)<120, nicht uniform-dunkel/ready/Endzustand. Schwarze/unklare Frames werden weiter gepollt (10×2,5 s); boss↔prep → nächster Versuch tippt den richtigen Button |
| A8a-2 | R2 wait_for_fight_end | `77f9c97` | FIXED — 3 Ready-Frames ohne je gesehenen Fight-Marker → 1× Battle (prep/boss, budgetiert), Wartefenster neu |
| A8b | R3 LAUNCHER/LOADING | `ac29638` | FIXED — LAUNCHER nur bei search>200 **und** pause>150; LOADING zählt im Auto-Loop nicht als Strike; Single-Loop akzeptiert LOADING als „gestartet“ |
| A8b | R4 _dim_probes | `1fe69a8` | FIXED — uniform-dunkle Transition ≠ Dim-Popup; Dim-Ende in wait_for_fight_end nur nach Debounce-Shot; Dim-Popup zählt nie als Fight-Marker |
| A8b | R5 back_to_ready | `6c7c186` | FIXED — Fight-Marker → wait_for_fight_end + resolve; sonst bis 20 Unknowns (~60 s) |
| A8b | R6 2x-Tap | `9c555b8` | FIXED — `set_speed_x2()`: tippt nur bei Fight-Marker, 1 Retry, sonst 1x + Log |
| A8b | R7 Chances | `450e4ff` | FIXED — OCR „Chances: N/7“ vor jedem Kampf (0 → sauberer Stop, Exit 0); Dim-Dialog direkt nach Battle → BACK, `'dialog'`, Lauf stoppt ohne Zählung. `start_fight` → `'started' \| 'dialog' \| None` |
| A8b | R8 Prune | `10d0ef5` | FIXED — dream (nicht bei --dry-run) + stage_push rufen `v.prune_shot_dirs()` (verschiebt nach `.spectre/trash`) |
| A8b | R9 Phantom-Win | `a9fcc43` | FIXED — RESULT zählt nur nach BATTLE/LOADING; sofortiges RESULT → 1 Re-Tap, sonst `battle_N_stale_result` + Stop |
| A8b | R10 PREP-Debounce | `880f77e` | FIXED — Wand nur bei PREP→PREP; BATTLE/LOADING/RESULT → weiter; CONFIRM → Cancel; sonst dritter Blick |
| A8b | R11 try_shot | `e4ad3d8` | FIXED — alle stage_push-Shots (außer wall_report) über `try_shot` (3 s Backoff), 5 Fehlschläge in Folge → `AdbDown` → **Exit 2** statt FATAL |
| A8b | R12 Popup-Fallback | `5425873` | FIXED — OCR „tap to close“/level/perk → Tap (960,540), Strikes auf 0; bei 15 Strikes einmal BACK + Mitte, dann Abbruch |
| A8c | R13 dream reach_world | `c713d43` | FIXED — Fight-Marker → abwarten; andere Unknowns 4× pollen; nie BACK auf UNKNOWN |
| A8c | R14 HERO_PROBE | `03c8745` | FIXED — Schwelle 170→180; Frame nach der 8. Resolve-Aktion wird bewertet; `REPO` weg |
| A8c | R15 toter POPUP-Check | `f531670` | FIXED — zweiter POPUP-Check + ungenutztes `arena` weg; (960,300)-Doppelnutzung dokumentiert (kein Verhaltenswechsel) |
| A8c | R16 Summary-Close | `5c1e2e3` | FIXED — alle drei Closes auf `CARD_CLOSE=(960,540)` |
| A8c | R17 parse_power | `a08a04b` | FIXED — erst aufwärts (i-1…i-8), dann i+1; Anker `Battle` + Satzzeichen |
| A8c | R18 wall_report | `b273afe` | FIXED — `log_error` getrennt; erster OCR-Aufruf je Prozess 30 s, danach 15 s |

## Geänderte Dateien

`scripts/afk_dream_realm.py`, `scripts/afk_stage_push.py`, `scripts/tests/fake_vision.py`,
`scripts/tests/test_runtime_fixes.py` (neu), dieser Bericht.

Neue Funktionen: dream `is_uniform_dark`, `is_fight`, `parse_chances`, `set_speed_x2`,
Konstanten `FIGHT_WAIT`, `MAX_UNKNOWN`, `SPEED_X2`, `FRAME_PROBES`; stage_push
`try_shot`, `AdbDown`, `ADB_FAIL_CAP`, `is_closable_popup`, `CARD_CLOSE`, `_run` (bisheriger
main-Körper; `main()` mappt `AdbDown` → 2).

## Bewusste Abweichungen vom Review

- **R17:** Anker nicht `^Battle\b`, sondern `Battle` + nur Satzzeichen — `^Battle\b` hätte
  „Battle Advice“ (Defeat-Karte, echte OCR) zum Anker gemacht.
- **R16:** kein zweiter Fallback-Punkt nach (960,540) — der einzige Kandidat war (960,1000).
- **R8:** kein Pro-Kampf-PNG-Limit im laufenden dream-Dir (würde Dateien löschen); das Dir
  wandert beim nächsten Lauf nach `trash`.
- **R14:** `is_dim_popup` bleibt (Dry-Run-Ausgabe nutzt es); globales Tap-Budget für
  start_fight/back_to_ready nicht erweitert (nicht im Prompt).

## Offen

- **Kalibrierung nur aus dem Report**, nicht an Frames nachgemessen (`.spectre` leer): v. a.
  `is_fight`-Profil, LAUNCHER-Gate (200/150), Dim-vs-Transition, HERO 180.
- **Frame-Manifest:** `classify_battle` hat sich geändert (LAUNCHER-Gate). Bei der R13-
  Neugenerierung mit `make_frame_manifest.py` (neue Frames) ist das automatisch drin;
  `--relabel` auf das alte Manifest geht nicht (Frames fehlen).
- `parse_chances` erwartet „Chances: N/7“ (Docstring) — echtes OCR-Format ungeprüft.

## Live-Check-Liste für Hermes

1. **Dream Start (R1/R6):** Lauf mit `--fights 1` → kein „started“ auf schwarzem Frame,
   `2x speed enabled` erst im Kampf; Shots `dr_f1_after*` prüfen.
2. **Pre-Fight hängt (R2):** falls die Prep-Seite stehen bleibt → `re-tapping Battle once` im Log.
3. **Chances (R7):** Log `chances left = N` stimmt mit der Anzeige; bei 0 `STOP: no Dream Realm chances left`.
4. **is_fight-Profil:** auf einem echten Kampf-Frame `True`, auf Boss/Prep/Ladebild `False`.
5. **Dim vs. Transition (R4):** nach Kampfende wird nur das echte Rewards-Popup weggetippt.
6. **HERO 180 (R14):** Hero-Karte nach Kampf wird weiterhin erkannt (Probe (474,1010) > 180?).
7. **Stage-Push Nacht (R3):** keine „game crashed“-Exit-3 mehr während Kämpfen; echter Launcher
   (Spiel geschlossen) → weiterhin Exit 3.
8. **Single-Push (R9):** `--battles 2` vom Victory-Screen → keine Phantom-Siege.
9. **Auto-Loop (R10/R12):** Level-/Perk-Popup mitten in der Kette → `closing via the card centre`;
   „wall reached“ erst bei PREP→PREP.
10. **adb weg (R11):** BlueStacks während eines Laufs stoppen → Exit 2 „adb down“, kein FATAL.
11. **Summary-Close (R16):** „Auto Battle Complete“ wird bei (960,540) geschlossen, Auto-Battle-
    Schalter bleibt unberührt.
12. **wall-report (R18):** neue Einträge mit `log_error` nur bei Schreibfehlern.
