# Claude Wave-2 Run — Abschlussbericht (2026-11-03)

Auftrag: Wave A komplett (A1 → A7c), offline, ein Branch pro Task, Commits lokal,
kein push/rebase/reset. Ergebnis: **A1–A6 fertig, A7 fertig bis auf zwei Punkte**
(F25 braucht Recon; F16-Prune nach Freigabe als „Papierkorb“ umgesetzt). Wave B übersprungen (RECON-Blöcke
leer), Wave C nicht angefasst, A8 nicht im Auftrag.

Testlauf (DoD, aus dem Worktree, echte Ausgabe):

```
$ python -m unittest discover -s scripts/tests -v
...
frame regression: checked=139 skipped=0 manifest=139
...
Ran 103 tests in 11.317s

OK
```

Pro Modul: test_frame_regression 1 (139 Frames), test_parsers 25, test_flows 17,
test_wall_dash 15, test_review_fixes 45 — alle ok, 0 skipped, 0 expected failures.

---

## ⚠️ Zuerst lesen: Git-Zustand (paralleler Writer)

1. **Shared Working Copy steht auf `feature/T48-helper-dedup`, nicht auf `main`.**
   Ich habe A1–A4 im geteilten Checkout `C:\Users\Sigi\spectre` per
   `git checkout -b` angelegt (die Regel „kein checkout“ kam erst mit der neuen
   `CLAUDE.md` in Hermes' Commit `621451a`). Hermes/Queue-Driver committen seither
   auf den ausgecheckten Branch: `621451a` (inkl. meines halbfertigen A4-WIP:
   `ocr_png`-Extraktion, `_level_hands.py`-Löschung) und danach 9 weitere Commits
   (`84d38b8` … `79671e6`, Doku/Infra) liegen auf `feature/T48-helper-dedup`.
   Ich habe nichts davon umgeschrieben (kein reset/rebase). **Hermes sollte den
   Shared-Checkout selbst wieder auf `main` stellen.**
2. Ab A5 habe ich in einem **eigenen Worktree** gearbeitet:
   `C:\Users\Sigi\spectre-claude-wt` (`git worktree add`), mit einer
   Junction `.spectre → C:\Users\Sigi\spectre\.spectre` (nur gelesen, gitignored),
   damit die Frame-Tests dort echte Frames finden. Aufräumen:
   `git worktree remove ../spectre-claude-wt` (Junction vorher löschen).
3. **Branch-Kette (gestapelt, jeder Branch enthält den vorigen):**
   `main(5eb7af3)` → T46 → T47 → T51 → `621451a`(Hermes) → T48(`539616d`) → T49 → T50 → T58.
   `main` ist inzwischen auf `13e959f` (T59) weiter → kein ff mehr.
   `git merge-tree` (Trockenlauf) ist **konfliktfrei** sowohl gegen `main` als auch
   gegen den T48-Tip mit Hermes' Zusatz-Commits. Einfachster Weg: `feature/T58-review-fixes`
   mergen (enthält alles), danach den T48-Tip (Hermes-Doku) separat.

| Task | Branch | Commits | Status |
|---|---|---|---|
| A1 T46 | `feature/T46-vision-harness` | `dac9438` | ✅ |
| A2 T47 | `feature/T47-parser-tests` | `2b8c354` | ✅ |
| A3 T51 | `feature/T51-mock-adb-flows` | `34eca63` | ✅ |
| A4 T48 | `feature/T48-helper-dedup` | (`621451a` Teil) + `539616d` | ✅ |
| A5 T49 | `feature/T49-wall-dash` | `1b97d0e` | ✅ |
| A6 T50 | `feature/T50-docs-sync` | `5be68cb` | ✅ |
| A7 T58 | `feature/T58-review-fixes` | 26 Commits `43048b8`…`95cba3f` (+ dieser Bericht) | ✅ außer F25 (Recon) |

---

## A1 / T46 — Offline Vision-Test-Harness

- Neu: `scripts/tests/__init__.py`, `make_frame_manifest.py`, `test_frame_regression.py`,
  `frame_manifest.json` (139 Frames, Text), `scripts/tests/.gitignore` (`.artifacts/`).
- `make_frame_manifest.py`: Globs `.spectre/shots-*`, **zusätzlich** `.spectre/shots`
  (Arena-Frames) und `.spectre/screens`; max. 2 Frames/Dir (erster+letzter);
  Felder `relpath, size, sha16, classify, battle_class`. Später ergänzt: `--relabel`
  (gleiche Frames, neue Verdikte — für gewollte Verhaltensänderungen; Diff zeigt
  genau die Flips). Generator-Header erklärt das.
- `test_frame_regression.py`: fehlende **oder geänderte** (sha16) Frames → skip + WARN.
- Generierung: 13,7 s (nicht 1–3 min). Ein Frame (`shots-14876/sp_wait.png`) wurde
  während des Laufs live überschrieben → zeigt, dass der sha-Skip nötig ist.
- Verteilung: classify PANEL 46 / WORLD 40 / UNKNOWN 33 / POPUP 21 (Stand A1).

## A2 / T47 — Parser-Unit-Tests

- Neu: `scripts/tests/test_parsers.py` (jetzt 25 Tests). Fixtures = echte WinRT-OCR
  aus `.spectre/wall-report.log` (Prep-Screen 254 / 74,986) und später echte OCR der
  Hero-Frames (`hl_entry`, `hl_710_0b`, `hl_840_1`).
- `parse_stage`, `parse_power` (Anker, Quest-Counter-Negativ, „Auto Battle“ kein
  Anker, Range), `read_level`, `ocr_lines` (Strip/Leerzeilen, List-Aufruf ohne shell,
  fehlende PNG → kein Subprozess, Timeout/OSError → `[]`), `ocr_text` rc≠0 → `[]`.
- `LvL99`/`LV.74`/`Lv.74986` waren zunächst `expectedFailure`; mit F2 grün.
- Import von stage_push/hero_level/claim_vision löst kein adb aus.

## A3 / T51 — Mock-ADB Flow-Tests

- Neu: `scripts/tests/fake_vision.py` (`FakeDevice`: patcht `v.adb/tap/swipe/shot/ocr_lines`
  + `time.sleep` + stdout, optional auch Modul-Kopien via `also=`; echter adb-Aufruf
  = Testfehler; Tap-/Shot-Log), `scripts/tests/test_flows.py`.
- Synthetische Frames („Blanko-Matrix“ im Modul-Docstring): WORLD/PANEL/POPUP/UNKNOWN,
  später BATTLE_MODES, ARENA_LOBBY/PREP, DIALOG, MENU, QUESTS, GIFT_ENTRY, EVENTS.
- Flows: normalize (UNKNOWN,UNKNOWN,WORLD → 0 + 2×BACK; 5×UNKNOWN → 1; WORLD → 0 Taps),
  Claim-Happy-Path (Taps exakt `GROUND, AFK_PROGRESS, CHEST, CLAIM, CLAIM, BACK`),
  Login-Popup (OCR „Daily Rewards“ → `LOGIN_CLAIM`; ohne Treffer → BACK, kein Claim).

## A4 / T48 — Helper-Dedup + `_level_hands.py`

- `afk_claim_vision.ocr_png(png, timeout=20, check_rc=False)` neu; `ocr_lines` delegiert.
- `afk_stage_push.ocr_text` = Adapter `v.ocr_png(png, timeout=15, check_rc=True)`
  (Timeout + rc-Semantik identisch); eigene POWERSHELL/OCR_PS1/subprocess entfernt.
- `afk_hero_level`: eigene ADB/tap/shot/OCR-Kopie + hardcodierte `C:\Users\Sigi`-Pfade +
  `SHOTDIR.mkdir` beim Import entfernt → `v.tap/v.shot/v.ocr_lines/v.adb`, Helfer
  `key()`, `snap()`. Shots jetzt im per-pid-Dir. **Verhaltensänderung:** fehlgeschlagener
  Tap/Screencap wirft jetzt (vorher still ignoriert).
- `scripts/_level_hands.py` gelöscht (landete in `621451a`, s. o.).

## A5 / T49 — Wall-Dash-Robustheit

- `load_events(path) -> (events, bad_lines)`: nur JSON-Objekte zählen; kaputte Zeilen
  und Nicht-Objekte (`null`, `123`, `[..]`) werden gesammelt; Leerzeilen ignoriert.
- `fmt_int`, `or_dash`: keine Crashes/„None“ bei null/String-Werten.
- CLI: `wrote … (N events, skipped M bad lines)` bzw. `no events, skipped M bad lines — widget not written`.
- Smoke auf Kopie des echten Logs: `wrote …real-wall.html (13 events, skipped 0 bad lines)`.
- Neu: `scripts/tests/test_wall_dash.py`.

## A6 / T50 — Doku-Sync

- `docs/afk-journey-guide.md`: neuer Abschnitt **Bot operation** — 3 Windows-Tasks
  (Night 02:00 / Daily 05:10 / Progress 17:10, Launcher-Kette), Night-Task (135 min,
  `--retry-defeats`, Retry-Cap 200, Wall-Report 1. + jede 10. Niederlage, Idle-Recheck),
  Marker-/Idle-Gate-Matrix, Phase-Normalizer, Login-Popup-Resolver, Lock-Keeper/Stale.
  Alles aus `afk-bot-watch.sh`, `afk-night.sh`, Launchern und argparse abgeleitet.
- `README.md`: Skript-Tabelle (EN) + Verweis (DE).
- `scripts/afk-bot-night.cmd`: veralteter Kommentar „4 h“ → „135 min“.

## A7 / T58 — Review-Fixes (1 Finding = 1 Commit)

Finding-Nr. `F<n>` = Position im Findings-Array von `docs/reviews/2026-11-03-scripts-review.md`.
Tests: `scripts/tests/test_review_fixes.py` (Klasse je Finding), Real-Frame-Tests skippen ohne Frames.

### Review-Korrekturen (Frame-Evidenz — bitte beachten)
- **F1:** `shots/arena_2_select.png`, `arena_f1_step0`, `arena_p1_pre` sind **nicht** der
  Kaufdialog, sondern der *Select Opponent*-Screen (visuell geprüft). stage_push' alter
  CONFIRM-Check feuerte genau dort (weiße Karte + grüner Schwerter-Button) — und **nie**
  auf einem echten Dialog, weil dessen gedimmter Hintergrund vorher als BATTLE galt
  (pause L 8–13). Der echte Dialog (`screens/arena_debug1.png`, „Spend 10 … Daily
  attempts 5/5“) und „Turn off Auto Battle mode?“ teilen ein Layout, Button-Reihe bei
  y≈711 **oder** y≈729.
- **F6:** `shots/arena_0_initial.png` ist das **Battle-Modes-Menü**, nicht die Welt.
  Echte False-Positives von `is_battle_modes`: Hauptmenü, Victory/Defeat/Battle-Ended,
  Ladetipps. Der Review-Vorschlag „AFK-Chip < 100“ hätte nichts getrennt.
- **F7:** `classify()` sagte WORLD auf **110 von 842** Frames, die keine Welt sind —
  u. a. ein **„1200% Special Limited Bundle“-Store-Popup** und ein **„Use Diamond“
  Cancel/Confirm-Dialog**. Alle 51 echten Welt-Frames haben den AFK-Chip L 103–174.
- **F17:** Review-Idee `'victory' in reason` wäre falsch — das echte Log enthält
  `battle_1_no_victory_prep` (Stillstand, kein Sieg).
- **F13:** Der „stale level“-Pfad ist im aktuellen Loop unerreichbar (Cap-Pfad liefert
  schon den frischen Wert) → nur defensiv gefixt.

### Commits
| Finding | Commit | Kern |
|---|---|---|
| F1 HIGH | `43048b8` | `v.is_confirm_dialog` (cremefarbenes Vollbreitenband + X/✓ auf Reihe 710 oder 729), `v.CONFIRM_CANCEL=(1014,710)` (im X auf beiden Reihen); stage_push prüft CONFIRM **vor** BATTLE; arena prüft vor jedem Kettenschritt. Manifest `--relabel`: 3 gewollte Flips |
| F6 HIGH | `b921d5b` | `is_battle_modes` + Routines-Icon (500,920) orange + Events-Icon (1160,940) dunkel: 25/25 Menü-Frames, 0 andere |
| F2 HIGH | `19acf40` | `read_level` case-insensitiv + `\b` + Glued-Guard (`Lv.74986`→74) + 1..300; `is_detail` lehnt Hall ab; `in_hall()` vor jeder weiteren Hand (Detail→Back, Stadt→Re-Entry (972,1034), sonst Stop); Exit 1 bei Fehlschlag |
| F17 HIGH (A7a-4) | `dd7f611` | `reason_family()`; Vokabular am Producer dokumentiert |
| F18 MED (A7a-4) | `5c8875c` | ISO-ts lokal; Stage/Power aus neuestem Event (`afk-state.json` schreibt niemand); `last` weg |
| F3/F4 HIGH (A7a-4) | in T49 `1b97d0e` | s. A5 |
| F5 HIGH | `b1664fa` | arena: Exit 1 wenn nichts gekämpft (STUCK/unverändert) → Marker wird nicht verbrannt |
| F19 MED | `a616c97` | arena.tap = `v.tap` (rc) + 1 Retry |
| F16 MED | `d41ca1f` | `idle_seconds`: `GetTickCount.restype=c_uint32`, `tick_delta()` 32-bit-wrap. Prune → s. u. |
| F7 MED | `b489d00` | WORLD nur mit leuchtendem AFK-Chip; Manifest: 15 Flips WORLD→UNKNOWN |
| F8 MED | `23cc75b` | `run_dailies(min_idle, pid, base)`, kein ARGS-Global, toter Zweig weg |
| F15 MED | `a5cf3c3` | `v.claim_round(tag, dry_run)` aus main extrahiert (A3-Tests unverändert grün); dailies nutzt es |
| F9 MED | `d5838cc` | `claim_quest_tabs()`: Tab nicht verifiziert → BACK + Panel neu öffnen; `open_menu` 5 Versuche, BACK auf Popups |
| F10 MED | `278a267` | gift: Panel-Check 3× + Entry-Re-Tap; „Entry nicht gefunden“ → **Exit 3** (statt 0) |
| F11 MED | `f8e879b` | gift: `claim_signal()` = dimmed ODER classify POPUP, ein Re-Shot |
| F12 MED | `0b54ec3` | hero: „Ressourcen leer“ erst nach 2 unveränderten x10-Taps |
| F13 MED | `0482993` | hero: letzter gelesener Level |
| F20 MED | `109bd97` | hero: Kauf-/Confirm-Dialog nach x10 → Cancel + Stop |
| F14 MED | `95cba3f` | hero: ein geschützter Hall-Entry-Retry via `in_hall` |
| F26 LOW | `bbc0180` | dump-Timeout → None, `swipe` prüft rc, `save_power_state` atomar |
| F27 LOW | `d580875` | claim_round: `reach_world()` statt blind BACK,BACK (BACK in der Welt = Exit-Dialog) |
| F28 LOW | `aebece2` | dailies: verifizierter Dismiss (+1 Retry), `TMP` weg |
| F29 LOW | `9f66a33` | gift: Swipe-Endpunkte geclampt (Origin (400,700) bleibt), `struct`/`TMP` weg |
| F30 LOW | `59c47a5` | gift: kein blinder (1500,600)-Tap; nur BACK bei unbekanntem Overlay |
| F21 LOW | `715491e` | arena: `sys.path` vor dem Import |
| F22 LOW | `24cc76d` | arena: tote reach_world/at_world + Doppelimport weg, Docstring |
| F23 LOW | `a9b69ca` | arena: `v.shot` (Handle zu, per-pid-Dir), lokale adb-Plumbing weg |
| F24 LOW | `4ee5581` | `--dry-run`-Hilfetexte nennen die verbleibenden Taps |
| F31 LOW | `f45a4f8` | hero: argparse |
| F32 LOW | A4 | `_level_hands.py` gelöscht |

### Neue Funktionen (Überblick)
`afk_claim_vision`: `ocr_png`, `is_confirm_dialog`, `CONFIRM_CANCEL/CONFIRM_ROWS`,
`tick_delta`, `claim_round`. `afk_hero_level`: `key`, `snap`, `is_hall`, `in_hall`,
`tap_x10`, `purchase_stop`, `HALL_BTN`, `LEVEL_MAX`. `afk_dailies`: `reopen_quests`,
`claim_quest_tabs`, `QUEST_TABS`, `is_dimmed`. `afk-daily-gift`: `wait_events_panel`,
`claim_signal`. `afk-wall-dash`: `load_events`, `fmt_int`, `or_dash`, `reason_family`,
`current`. Tests: `make_frame_manifest.relabel`, `fake_vision.FakeDevice/frame`.

---

## F16-Prune (nach Freigabe umgesetzt)

War zuerst blockiert (Auto-Mode-Classifier: unwiderrufliches Löschen von
`.spectre`-Laufzeitdaten). Entscheidung des Owners: **in einen Papierkorb verschieben**.
`v.prune_shot_dirs(root, keep=30)` verschiebt beim Start von `afk_claim_vision`
(nicht bei `--dry-run`) alle `shots-<pid>`-Dirs außer den 30 neuesten und dem eigenen
nach `.spectre/trash/` (Namenskollision → `.1`, `.2`, …; gesperrte Dirs → nächster Lauf).
**Es wird nichts gelöscht — der Platz wird erst frei, wenn `trash/` von Hand geleert wird.**

Zwischenfall beim Bauen: Die A3-Claim-Tests rufen `v.main()` auf; im ersten Testlauf hat
die neue Funktion dadurch 92 echte Dirs nach `.spectre/trash/` verschoben (nichts
gelöscht). Ich habe alle 92 sofort zurückverschoben (0 Konflikte, `trash/` entfernt,
122 Dirs wieder an ihrem Platz, mtimes unverändert). `FakeDevice` stubbt
`prune_shot_dirs` jetzt; Kontrolle danach: 122 vorher/nachher, kein `trash/`.

## Nicht gemacht / offen

- **F25 (arena_state Lobby→PREP)** + **neuer Befund N2**: Der Live-Fehlschlag 11-03 00:45
  („step 1–5: RESULT … STUCK“) kommt daher, dass nach dem Tipp auf den linken Gegner
  eine **Gegner-Detailkarte mit grünem „Challenge!“-Button** (~(1200,1005), Frame
  `shots/arena_f1_step1.png`) erscheint; `arena_state` liest sie als RESULT und tippt
  (480,300). Der T27-Ablauf „Gegner tippen → Kampf läuft automatisch“ stimmt nicht mehr.
  **> RECON nötig:** Koordinate „Challenge!“ auf der Detailkarte, Folgescreen (Prep? direkter
  Kampf?), Probe für DETAIL. Nicht blind gebaut.
- **Wave B (B1–B6):** übersprungen — in `docs/claude-wave-2-plan.md` gibt es keine gefüllten
  `> RECON:`-Blöcke (nur die Aufgabenbeschreibung „RECON (Hermes): …“).
- **A8 (T59 Runtime-Fixes):** kam während des Laufs per Hermes-Commit in Plan/Prompt;
  nicht Teil meines Auftrags (A1–A7c) → nicht angefangen.
- **F9-Rest:** veraltetes Panel des vorigen Tabs besteht `is_quests_panel` weiterhin
  (braucht tab-spezifische Probes → Recon).
- **F10-Rest:** zweites Pixel für den Gift-Entry (Bubble-Outline) → Recon.
- Parser-Grenzen: `Lv199` (OCR von „LvL99“?) → 199, `Lv. 1234` → 123 — prinzipiell nicht
  unterscheidbar.
- **N3:** Progress-Run ruft `afk_stage_push.py` **ohne `--min-idle`** auf (watch.sh Z. 135) —
  nur der Chest-Schritt ist idle-gated. Nicht geändert (Scheduler = Hermes-Lane), in der
  Doku-Matrix vermerkt.
- **N4:** `afk-night.sh` verschluckt den Push-Exit-Code (tee ohne pipefail) — Hermes hat das
  parallel als R12 erfasst; in der Doku vermerkt.

## Verhaltensänderungen, die Hermes kennen muss

- `afk-daily-gift.py`: „kein Entry gefunden“ → **Exit 3** (Marker wird nicht geschrieben).
- `afk_arena.py`: Exit 1 wenn nichts gekämpft; Shots jetzt in `.spectre/shots-<pid>/arena_*`
  (nicht mehr `.spectre/shots/`); Tap-Fehler werfen nach 1 Retry.
- `afk_hero_level.py`: Exit 1 bei unlesbarer/fehlender Hand oder verlorener Hall; Shots im
  per-pid-Dir; Kaufdialog nach x10 → Cancel + Stop.
- `classify()`: WORLD nur noch mit leuchtendem AFK-Chip → Kampf-/Menü-Frames sind jetzt
  UNKNOWN (Driver verweigern; `afk_normalize`/`reach_world` tippen dort BACK).
- `classify_battle`: CONFIRM vor BATTLE → im Auto-Loop wird „Turn off Auto Battle?“ jetzt
  **abgebrochen** (1014,710) statt Skip-Tap hinein.
- `afk_dailies`: unbestätigter Chest-Claim → Exit 1 (vorher weiter); gescheiterte Tabs →
  BACK + Panel neu öffnen.
- `afk-wall-dash.py`: liest keine `afk-state.json` mehr.

## Live-Check-Liste für Hermes

1. **Kaufdialog-Gate (F1):** Arena mit 0 Versuchen öffnen → Log `STOP: daily arena attempts
   exhausted (purchase dialog cancelled)`, Tap auf (1014,710) schließt den Dialog; Diamanten unverändert.
2. **„Turn off Auto Battle?“ (F1):** im Auto-Push provozieren → Dialog wird gecancelt, Auto läuft weiter.
3. **Battle Modes (F6):** `afk_arena.py --dry-run` aus der Welt → Menü wird erkannt; aus dem
   Hauptmenü heraus → kein falsches „open“.
4. **WORLD-Gate (F7):** `afk_claim_vision.py` auf Welt (Tag + Nacht) → `initial state: WORLD`;
   auf Battle-Modes-Menü → `UNKNOWN` (kein Tap). `afk_normalize.py` während eines Kampfs
   beobachten (BACK könnte einen Kampf-Pause-Dialog öffnen).
5. **Hero-Level (F2/F12/F20/F14):** `afk_hero_level.py --target <aktuell+10>` → Hall-Re-Verify
   zwischen Händen im Log, Exit-Code prüfen; Level-OCR gegen Badge.
6. **Arena-Exit (F5):** einen STUCK-Lauf → Exit 1, `arena-last.txt` bleibt alt.
7. **Arena-Detailkarte (N2):** Recon „Challenge!“ auf der Gegner-Detailkarte + Folgescreen.
8. **Gift (F10/F11):** Daily-Gift an einem Tag mit Claim → `claimed row … (Rewards Obtained, <Signal>)`;
   Tag ohne Entry → Exit 3; Pan-Swipes (geclampt) finden den Entry weiterhin?
9. **Dailies (F9/F15):** Quest-Tabs lucky/growth/guild → BACK+Reopen im Log; Chest via `claim_round`.
10. **Wall-Dash:** `python scripts/afk-wall-dash.py` → Walls/Progress > 0, Stage/Power aus Events,
    Zeit lokal statt ISO.
11. **idle_seconds (F16):** nach >24,8 Tagen Uptime keine Dauer-SKIPs mehr (nicht offline prüfbar).
12. **F16-Prune:** erster Daily-Run → Log `moved N old shot dirs to .spectre/trash/`, 30 `shots-*` bleiben; `trash/` regelmäßig leeren.

## Annahmen

- Branches gestapelt (jeder Task baut auf dem vorigen), weil spätere Tasks die Tests/Helfer
  der früheren brauchen.
- `.spectre/shots` (ohne Bindestrich) zusätzlich zu den Default-Globs ins Manifest aufgenommen
  (Arena-Frames).
- F14/F20 (MED aus dem Review, nicht in der Plan-Kurzliste A7b) mitgenommen — billig und
  sicherheitsrelevant (F20: „never diamonds“).
