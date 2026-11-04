# Claude Wave-6 Run (F1–F5 / T81–T85) — Sammelbericht (2026-11-04)

Auftrag: Rollout der Wave-5-Fast-Paths (afk_memory, ocr_region, tap_seq), Dura's in den Tageslauf,
Frida/Speed-Profil betriebsreif. Offline, kein push, keine neuen Dependencies, `.spectre` nur
read-only gelesen (Frames als Kopie im Scratch), `TODOS.md` nicht angefasst. Basis `main` `fbc2660`
(Brief); Branches je in eigenem Worktree (`C:\Users\Sigi\spectre-w6-T81` … `-T85`, ohne Junction).

Ablauf je Task (Workflow, 20 Agenten): Implementierung im eigenen Worktree → zwei unabhängige
Read-only-Reviews (Linse 1: Verhaltenserhalt/Sicherheit; Linse 2: Brief-Treue, Teststärke,
übersehene Stellen) → Fixer prüft jeden Befund gegen den Code, setzt die echten um, volle Suite,
**ein** Commit. Danach habe ich jeden Produktions-Diff selbst gelesen und den Probe-Merge gefahren.

| Task | Branch | Commit | Suite auf dem Branch | Review |
|---|---|---|---|---|
| F1/T81 afk_memory-Rollout | `feature/T81-afk-memory-rollout` | `a81d6b4` | `Ran 335 tests … OK (skipped=22)` | 1 Befund, umgesetzt |
| F2/T82 Region-OCR-Rollout | `feature/T82-region-ocr-rollout` | `e417b4e` (+ dieser Bericht) | `Ran 342 tests … OK (skipped=26)` | 5 umgesetzt, 1 abgelehnt |
| F3/T83 tap_seq-Rollout II | `feature/T83-tapseq-rollout` | `53b3aee` | `Ran 342 tests … OK (skipped=22)` | 2 umgesetzt |
| F4/T84 Dura's aktivieren | `feature/T84-duras-daily` | `192d478` | `Ran 342 tests … OK (skipped=22)` | 4 umgesetzt |
| F5/T85 Speed-Profil betriebsreif | `feature/T85-speed-profile-ops` | `a775d41` | `Ran 349 tests … OK (skipped=22)` | 9 umgesetzt |

(Branch-Suiten gegen Basis `fbc2660` = 333 Tests.)

**Probe-Merge** T81–T85 auf den aktuellen `main` `3d92f18` (inkl. Hermes' mem_probe/read-batch-Fix;
detached HEAD in `C:\Users\Sigi\spectre-w6`, kein Branch bewegt): **konfliktfrei**,
**`Ran 379 tests in 72.070s — OK (skipped=26)`**. `main` allein: `Ran 334 tests … OK (skipped=22)`;
334 + 2 + 9 + 9 + 9 + 16 = 379 ✓. Die 4 neuen Skips = T82-Real-Frame-Tests (Worktrees haben kein
`.spectre`). Kein Rust geändert (cargo nicht nötig).

**Eigene Gegenprobe T82** (unabhängig von den Agenten): alle 21 echten `hl_*`-Frames aus
`.spectre/shots-*` in den Scratch kopiert, gemergten `hall_lines` gegen Voll-OCR laufen lassen:
**21/21 gleiches Urteil, 7/7 Hall-Treffer allein über die Region, 0 Fehltreffer.** Einschränkung: alle
7 Positiv-Frames stammen aus einer Session (`shots-69252`).

## F1/T81 — afk_memory-Rollout

- `afk-daily-gift.py`, `afk_claim_vision.main`, `afk_dream_realm.py`, `afk_stage_push.py` rufen
  `afk_memory.power` statt `v.memory_preflight`; Logzeilen und ok/disabled/fail-Zweige byte-identisch
  (von mir im Diff geprüft). `afk_claim_vision` importiert `afk_memory` lokal in `main()`
  (Zirkularimport; zweite Modulinstanz harmlos, nur Konstanten).
- Regel im `afk_memory`-Docstring: „kein Skript liest Offsets direkt, wenn afk_memory reicht".
- Tests (`TRollout`): Wiring-Check pro Konsument + grep-Assert über `scripts/*.py` (Guard-Helfer
  `memory_preflight(`/`read_power(`/`read_power_entry_valid(`/`revalidate_power_offset(`/
  `adb_exec_dump(` und — nach Review — direkte `spectre … dump/read/read-batch`-Aufrufe; Allowlist
  `afk_memory.py`, `afk_claim_vision.py`, `wallet-hunt-all.py`). Mutationsprobe: Rückbau eines
  Konsumenten bzw. eingefügter `spectre read`-Aufruf → Test rot.
- Bewusst unverändert: Recherche-Tools (`mem_probe`, `wallet-hunt-all`, `*-hunt.sh`,
  `ui-state-verify.sh`) und die pid/base-Ermittlung (`spectre find/regions`) in den Wrappern.
- Zwischenfall (vom Agenten gemeldet, behoben): ein `git checkout-index -f` während der Mutationsprobe
  setzte die ungesicherte Änderung in `afk_stage_push.py` kurz zurück; aus Sicherung wiederhergestellt —
  der committete Stand enthält die Umstellung (von mir im Branch-Diff bestätigt).

## F2/T82 — Region-OCR-Rollout

**Umgestellt** (`scripts/afk_hero_level.py`, Helper `hall_lines`): Hall-Gate in `main` (`hl_entry`)
und die drei `is_hall`-Prüfungen in `in_hall` (`tag`, `{tag}_b`, `{tag}_reenter`).
Muster: zuerst `v.ocr_region(name, HALL_BOX)`; ohne „Resonance Level"-Zeile folgt die bisherige
Voll-OCR. Negative (inkl. `is_detail`) verhalten sich daher identisch.

- `HALL_BOX = (740, 315, 1180, 405)`, gemessen an `.spectre/shots-69252/hl_entry.png`
  (Text ca. x 862..1110, y 345..370). LIVE: auf dem Gerät noch nicht gelaufen.
- Verifiziert auf 21 echten `hl_*`-Frames: 7 Hall-Treffer (hl_entry, hl_daily_hall0/1,
  hl_scan_hall_850/970/1090/1210), 14 Nicht-Hall-Frames (Detail hl_scan_*, hl_daily_pre*/post1,
  Quest-Panel shots-47096/hl_entry*). Region und Voll-OCR liefern überall dasselbe Urteil.
- `FakeDevice` faked jetzt auch `ocr_region` (→ `[]`), damit kein Test über `v.TMP` echte Dateien liest.

**Messnotiz** (WinRT über PowerShell, Median aus 5 Läufen, Frames als Kopie im Scratch):

| Frame | Voll-OCR | Region | hall_lines |
|---|---|---|---|
| hl_entry (Treffer) | 0,73 s | 0,57 s | 0,58 s |
| hl_scan_970 (Miss, Detail) | 0,53 s | 0,61 s | 1,12 s |

Ersparnis pro positivem Hall-Check etwa 0,15–0,3 s (rund 20–30 %); der Start von
PowerShell/WinRT dominiert. Ein negativer Check kostet etwa +0,6 s (Region plus Fallback).
Negative sind selten (Detail noch offen / Stadt). Die Werte schwanken je nach Last
(Reviewer haben 0,9 vs. 0,68 s bzw. 2,05 vs. 1,11 s gemessen); die Richtung ist überall gleich.
Ehrlich: der Gewinn ist klein, weil der PowerShell-Start pro OCR-Aufruf dominiert (s. Offene Punkte).

**Nicht umgestellt** (kein echter positiver Frame unter `.spectre/shots-*`, oder kein Gate):

- `afk_claim_vision.resolve_startup_popup` (Login-Popup): kein Popup-Frame, keine `claim_*`-Frames.
  „Daily Rewards" steht nur in der Arena-Lobby.
- `afk_stage_push` `is_auto_complete` (:351/:357/:491/:633): kein Frame mit „Auto Battle Complete".
- `afk_stage_push.wall_report` (:208): kein Gate; braucht die vollen Zeilen für den JSONL-Bericht.
- Hero-Detail-Parser (`read_level`, `resources_ok`, „within 10"): brauchen die vollen Zeilen als Daten.
- `afk_device_ready.is_title`, `afk_normalize` :54, `afk_duras.read`: keine passenden Frames.
- `afk_dream_realm.parse_chances` (:575): positive Frames gibt es nur in `.spectre/trash/`
  (`dr_f*_chances.png`) und `.spectre/livecheck/now.png`, also außerhalb des Scopes `shots-*`.

Damit ist vom Ziel „entry/claim/stage-prep" nur **entry** erreicht; claim (Login-Popup) und
stage-prep/auto-complete brauchen einen Live-Capture (Hermes), danach dasselbe `hall_lines`-Muster.

## F3/T83 — tap_seq-Rollout II

Umgestellt, jeweils `tap_seq(..., tolerate=False)` mit identischen Waits und Tap-Reihenfolge
(von mir im Diff geprüft; Gates bleiben vor dem Batch, kein Read wird übersprungen):

1. `afk_hero_level.daily_charge`: Panel- + Confirm-Tap auf `LEVEL_X1` (Money-Path, `LIVE:`-Marker).
2. `afk_dailies.run_dailies`: nach dem `is_dimmed`-Gate DISMISS + BACK (sonst BACK allein wie bisher).
3. `afk-daily-gift`: zweite Dim-Ebene + schließender BACK in einem Batch; `closed`-Flag verhindert den
   doppelten BACK (`LIVE:`-Marker).

- BACK-Ketten in hero_level geprüft: keine direkt aufeinanderfolgenden `key(4)`; gemischte
  tap+key-Folgen bleiben (kein gemischter Helper).
- Tests je Umstellung (Tap-Reihenfolge, echte Shell-Zeile inkl. Timeout, RuntimeError bei rc≠0);
  neuer Test-Helper `fake_vision.real_seq`. Bestehende Erwartungen unverändert.
- Review-Befund rc-Vertrag (berechtigt, betrifft meinen Wave-5-Helper): `_run_seq` verbindet mit `;`,
  der geprüfte rc ist der des letzten `sleep` — ein fehlgeschlagenes `input tap` im Batch wird nicht
  erkannt, `tolerate=False` fängt nur adb-Transportfehler. In T83 nur dokumentiert (Docstring);
  Umstellung auf `&&` = Follow-up (s. Offene Punkte).

## F4/T84 — Dura's im Tageslauf

- `afk-bot-watch.sh` (Daily/`--scheduled`): neuer Block nach dem Leveling, direkt vor dem Stage-Push,
  1:1 nach dem T67-Muster: `AFK_DURAS` (Default 1), Tagesmarker `$OUT_DIR/duras-last.txt` (UTC) nur
  bei rc 0/4, `normalize_or_abort` davor, `--min-idle`, jeder andere rc weich (Log, kein Marker, Kette
  läuft, Daily-Exit unverändert). `afk-night.sh` bewusst nicht (Night = nur Stage-Push).
- Härtung `afk_duras.py` (alle Koordinaten/Wörter bleiben Konstanten oben):
  - Tap-Lock nach Hausmuster (exit 7; im Wrapper über `AFK_BOT_LOCK_HELD` geerbt).
  - `first_clear`: „hängt" (keine Ergebniskarte / falscher Screen) → rc **1** statt 4, damit ein
    hängender Lauf den Tag nicht als erledigt markiert; nicht geschafft / Dialog → 4.
  - Neuer Schalter `PREP_GATE = True` (LIVE): `FIGHT_BTN` nur, wenn `sp.classify_battle` PREP liest —
    vorher wurde nach Challenge blind „Battle" getippt.
  - Tokens werden nie gekauft (Dialoge immer CANCEL, bestehender Pfad).
- Tests: 2-Läufe-Gate, weich bei rc 1, Marker bei 0/4, Schalter, Reihenfolge (nach Claims, vor
  Stage-Push), Prep-Gate. **Begründete Test-Änderung:** in 4 bestehenden `test_duras`-Tests ist das
  Frame nach Challenge jetzt `SP_PREP` statt `UNKNOWN` (das neue Gate verlangt den Prep-Screen);
  erwartete Ergebnisse unverändert. Lock-Wiring-Test um `afk_duras.py` ergänzt; Doku
  (`agent-workflow.md`, `afk-journey-guide.md`) nachgezogen.
- Gate-Semantik wie Leveling: rc 1/5/7 → kein Marker → nächster Watch-Lauf versucht es am selben Tag
  erneut. „Genau 1 Versuch/Tag" gilt also für saubere Ausgänge.

## F5/T85 — Speed-Profil betriebsreif

- Konstanten mit `LIVE: HERMES-SETUP`: `SERVER=/data/local/tmp/frida-server`, `DEFAULT_PORT=27142`
  (`FRIDA_PORT` überschreibt).
- Versions-Konsistenz: `frida --version` (PC) vs. `<SERVER> --version` (Gerät, via su) — Abweichung oder
  leere Server-Ausgabe → rc 4 mit beiden Werten.
- rc-Semantik im Docstring: 0 ok · 2 Spiel läuft nicht / Eingabe · **3 frida fehlt** · **4 Server
  tot/unerreichbar/Version passt nicht/kein Root/adb hängt** · 5 frida-Timeout. Ein frida-eigener
  Exit-Code ≠ 0 wird durchgereicht (kann mit 3/4/5 kollidieren; dokumentiert, `error` gesetzt).
- `status --json`: genau **ein** JSON-Objekt auf stdout (`rc`, `frida`, `server{running,version,port}`,
  `timescale`, `error`); `status` ist read-only (startet/pusht keinen Server, toter Server → rc 4);
  adb-Timeout/OSError → rc 4 statt Traceback.
- README `hack/frida/README.md`: Abschnitt „Speed-Profil" (Nutzung, rc-Tabelle, Port/Version,
  `status --json`-Beispiel, Env-Gate, OFF/Restart mit `--repeat-ms`); Schritte 4/5 auf Port 27142 +
  `adb forward` + `attach.py --host` korrigiert (vorher zeigte der manuelle Pfad auf 27042).
- Nicht im Tageslauf: Test stellt sicher, dass kein Wrapper (`*.sh`, `*.py`, `*.cmd`, `*.ps1`)
  `speed_profile` referenziert.
- Alle Pfade gemockt (rc 3, rc-4-Varianten, JSON-Form/Parsebarkeit, on/off-Kommandozeilen, dry-run).

## LIVE-Check-Liste (Hermes)

1. T81: je ein Lauf `afk-daily-gift`, `afk_dream_realm`, `afk_stage_push`, `afk_claim_vision` mit
   `--pid/--base` → Log `preflight team_power = …` wie bisher.
2. T82: Hall-Eintritt im Leveling — Zeile `hall open: Resonance Level …` kommt aus der Region
   (Shot `hl_entry_r.png` vorhanden); ggf. Box an neuem Frame nachmessen.
3. T83: Daily-Charge (Money-Path): Preview-Panel öffnet sich noch mit On-Device-`sleep 2.5` vor dem
   Confirm; Dailies-Dim + Gift-Doppel-Dim im Feld.
4. T84: erster Daily mit Dura's — `DURAS_CARD`, `CHALLENGE_BTN`, Prep-Gate (`sp.BATTLE_BTN` grün auf dem
   Dura's-Prep?), `SWEEP_BTN`, `RESULT_CLOSE`, OCR-Wörter; nur Konstanten oben korrigieren.
5. T85: frida-server auf 27142 (oder `FRIDA_PORT`), `--version`-Ausgabeformat beider Seiten,
   `/proc/net/tcp` via su lesbar, dann `status --json` → `on --scale 1.5` → Wallzeit gegen T61 → `off`.

## Offene Punkte / Follow-ups

- **tap_seq rc-Vertrag** (Wave-5-Helper): `&&` statt `;` in `_run_seq`, damit ein fehlgeschlagener
  Tap den Batch stoppt und `tolerate=False` greift wie bei `v.tap`; betrifft alle Wave-5/6-Aufrufer
  und den Dry-Line-Test.
- T82: Login-Popup- und Auto-Complete-Frames live capturen, dann umstellen. Der eigentliche OCR-Hebel
  ist der PowerShell-Start pro Aufruf (~0,5 s) — ein persistenter OCR-Prozess würde mehr bringen als
  weitere Boxen.
- T81: grep-Assert ist zeilenbasiert (mehrzeilige/dynamische spectre-Aufrufe fallen durch).
- T85: `timescale` ist bei `status` meist `null` (frida `-q` endet vor dem Probe-Intervall) — nach
  Live-Check ggf. frida `-t/--timeout`.
- Nebenbefund T82: die Arena-Lobby zeigt „Daily Rewards" — `resolve_startup_popup` würde dort feuern,
  falls `classify` je POPUP liefert.
