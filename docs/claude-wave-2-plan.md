# Claude Wave-2 — Plan & Briefs (2026-11-03)

> **Zweck:** Nächste Ausbaustufe des Spectre/AFK-Bots — so zugeschnitten, dass
> Claude Code sie **ohne Live-Gerät** (BlueStacks/adb gehören Hermes) umsetzen
> kann. Jede Aufgabe ist offline baubar + offline testbar; Live-Verifikation
> macht Hermes in einem separaten Schritt.
>
> **Reihenfolge:** Mit Wave A sofort starten (A1 zuerst). Wave B braucht vorher
> Hermes-Recon (Koords/Probes), die Platzhalter `> RECON:` unten werden von
> Hermes gefüllt, danach werden die B-Briefs an Claude gefüttert.

---

## 0. Spielregeln für diese Wave (Safeguard-freundlich)

1. **Offline only.** Kein Task startet BlueStacks/apps, tippt live oder ruft
   echte adb-Befehle. Alles läuft über Dateien/Tests.
2. **`.spectre/` ist read-only Input** (gitignored Runtime-Daten: Screenshots,
   Logs) — Ausnahme: `.spectre/logs/` (dort schreibt `bluestacks-ensure.sh` sein Log).
   Neue Artefakte schreibt nur `scripts/tests/.artifacts/`.
3. **Keine neuen Dependencies.** Nur Python-Stdlib + vorhandenes `PIL`
   (Interpreter: `python` in dieser Shell, 3.14.9, PIL vorhanden).
   Kein pytest — **stdlib `unittest`**.
4. **Append-only wo möglich.** Neue Tests/Funktionen bevorzugt HINZUFÜGEN,
   bestehende Logik nur anfassen wenn der Brief es sagt. Hält Merge-Konflikte
   mit dem parallel laufenden Queue-Driver klein.
5. **`TODOS.md` gehört dem Queue-Driver** (Cron). Claude editiert es NICHT.
   Statusmeldungen kommen in den Abschlussbericht.
6. **Ein Branch pro Task** (`feature/T{NN}-...`), Commit lokal auf dem Branch.
   Push/Merge macht Hermes (Queue-Driver hält `main` grün).
7. **Frames sind lokal, nicht im Git.** Test-Manifeste referenzieren Pfade
   unter `.spectre/**`; fehlt ein Pfad (Rotation/Prune), wird der Eintrag
   übersprungen — Tests bleiben grün, Warnung im Output.
8. **DoD pro Task:** Task-Tests laufen grün (`python -m unittest ...`),
   keine Änderung an bestehenden Test-Erwartungen ohne Begründung im Report.
   Abschlussbericht: geänderte Dateien, neue Funktionen, Testausgabe (echte
   Zeilen!), OFFENEs/Unsicherheiten, Live-Check-Liste für Hermes.

### Was wenn Claude blockt — Fallback & Tricks

| Wenn Claude … | Trick / Workaround | Owner |
|---|---|---|
| `powershell.exe -ExecutionPolicy Bypass` (OCR) suspekt findet | Ist offline + signiert; alternativ Wrapper `scripts/ocr.cmd` nutzen; subprocess-List-Aufruf statt shell=True zeigen | Claude |
| sich nicht sicher ist, ob Taps das Spiel stören | Brief sagt: „Gerät gehört Hermes; Task fasst NUR Dateien an" | Claude |
| bei `unittest`-Discover auf Import-Fehler läuft | Tests importieren via `sys.path.insert(0, str(Path(__file__).parents[2] / 'scripts'))` — Snippet liegt in jeder Testdatei | Claude |
| bei `.spectre` (112 shot dirs, 779 PNGs) „zu groß" ruft | Harness nimmt max. 2 Frames pro dir; Manifest ist Text | Claude |
| neue Libs (pytest/numpy) installieren will | Regel 3 zitieren: stdlib; PIL ist da (`python -c "import PIL"`) | Claude |
| beim großen `afk_stage_push.py` Kontext verliert | Briefe nennen Funktionsname + Zeilenbereich; gezielt lesen | Claude |
| einen Task nicht abschließen kann (ungeklärte Koords) | Platzhalter `> RECON:` dokumentieren; Hermes liefert nach; Rest weiterbauen | Hermes |
| komplett blockt / ablehnt | Hermes baut den Task (Fallback-Lane), Claude bekommt den nächsten | Hermes |

---

## 1. Wave A — sofort, offline (Branch pro Task)

### A1 / T46 — Offline Vision-Test-Harness (ZUERST)
**Ziel:** Regressionstests für `classify()` (afk_claim_vision) und
`classify_battle()` (afk_stage_push) auf echten Frame-Screenshots — damit
Vision-Änderungen künftig ohne Live-Gerät prüfbar sind.

**Neu:** `scripts/tests/__init__.py`, `scripts/tests/make_frame_manifest.py`,
`scripts/tests/test_frame_regression.py`, `scripts/tests/frame_manifest.json`.

**Vorgehen:**
1. `make_frame_manifest.py`: scannt `.spectre/**/*.png` (Default-Globs:
   `.spectre/shots-*/`, `.spectre/screens/`; max. 2 pro Verzeichnis),
   lädt je Bild, ruft die beiden Classifier, schreibt JSON-Liste
   `{relpath, size, sha16, classify, battle_class}`.
2. `test_frame_regression.py`: lädt Manifest; pro Eintrag mit existierender
   Datei → `assertEqual(classify(img), entry['classify'])` (+ battle_class);
   fehlende Dateien: skip mit Warnung; am Ende `print` der Zähler
   (checked/skipped).
3. Manifest in `main` committen (Textdatei, klein).

**DoD:** `python -m unittest discover -s scripts/tests -v` → alle grün,
checked ≥ 100 Frames lokal; belegt echte Testausgabe im Report.
**Hinweis:** Das Manifest „lockt" den aktuellen, review-gesegneten Stand.
Bei gewollter Verhaltensänderung wird es bewusst neu generiert (Header-Kommentar
im Generator erklärt das).

### A2 / T47 — Parser-Unit-Tests
**Ziel:** Der `74`/`74,986`-Kollisionsklasse von Fehlparsern vorbeugen.

**Neu:** `scripts/tests/test_parsers.py`. Tests für:
- `afk_stage_push.parse_stage` / `parse_power` (Anker-Regeln, Quest-Counter-
  Negativfälle, Power neben „Battle"-Zeile, `None` bei Fehlanzeige),
- `afk_hero_level.read_level` (`'Lv. 74'`→74, `'LvL99'`→99, Power-Zeile
  `'74,986'` allein → None, `'Lvl.99'`),
- `afk_claim_vision.ocr_lines`-Output-Behandlung (Fixture-Textzeilen).

**DoD:** neue Tests grün; je Parser mind. 1 Negativ-Fixture.
**Hinweis:** Import beider Skripte darf kein adb auslösen (Modul-Level prüfen;
falls doch: Import bleibt, nur Funktionen testen).

### A3 / T51 — Mock-ADB Flow-Tests (Kern-Flows offline)
**Ziel:** Zustandsmaschinen ohne Gerät testen können.

**Neu:** `scripts/tests/fake_vision.py` (Monkeypatch-Helfer: ersetzt
`v.adb/v.tap/v.shot/v.ocr_lines` durch gescriptete Frames + Tap-Log),
`scripts/tests/test_flows.py`.

**Vorgehen (klein anfangen):**
1. `afk_normalize.main()`: Sequenz `UNKNOWN→UNKNOWN→WORLD` → Exit 0,
   genau 2 BACK-Taps; Sequenz 5×UNKNOWN → Exit 1; erster Probe WORLD → 0 Taps.
2. Claim-Happy-Path aus `afk_claim_vision.main`: WORLD→PANEL→POPUP(chest)→
   POPUP(after claim)→PANEL → Exit 0; Tap-Reihenfolge im Log geprüft.
3. Login-Popup: `v.ocr_lines` liefert „Daily Rewards" → LOGIN_CLAIM wird
   getappt; ohne OCR-Treffer → BACK statt Claim.

**DoD:** Tests grün, Tap-Logs exakt (Position + Reihenfolge).
**Hinweis:** Frames können synthetisch sein (Solid-Color-PNGs via PIL mit den
richtigen Probe-Farben) — echte Screenshots wären besser, aber synthetisch ist
für den Start OK (Blanko-Matrix im Test dokumentieren).

### A4 / T48 — Helper-Dedup + Tote Datei (R9)
**Ziel:** `afk_hero_level.py` nutzt die Helfer aus `afk_claim_vision`
(`v.tap/v.shot/v.ocr_lines/v.idle_seconds/v.BACK`) statt eigener Kopien;
eigene `subprocess`-Plumbing-Block entfernen. `afk_stage_push.ocr_text` auf
`v.ocr_lines` vereinheitlichen (Adapter für Path↔Name-Signatur, Fehler-
schlucken identisch halten). `scripts/_level_hands.py` löschen.

**DoD:** `python -c "import ast; ..."` ok; A1/A2/A3-Tests bleiben grün;
Verhalten unverändert (keine Koord-/Ablaufänderung).

### A5 / T49 — Wall-Dash-Robustheit
**Ziel:** `afk-wall-dash.py` gegen kaputte JSONL-Zeilen/Nulls härten.

**Vorgehen:** Parse-Teil in `load_events(path) -> tuple[list[dict], list[str]]`
extrahieren (garbage lines werden gesammelt, nicht geschluckt); Tests in
`scripts/tests/test_wall_dash.py`: leere Datei, fehlende Datei, Null-Felder,
kaputtes JSON, gültig+kaputt gemischt → Ausgabe zählt `bad_lines`.

**DoD:** Tests grün; CLI-Ausgabe („wrote … events, skipped N bad lines").

### A6 / T50 — Doku-Sync
**Ziel:** `docs/afk-journey-guide.md`: neue Betriebs-Features dokumentieren —
Night-Task (02:00, 135 min, Retry-Defeats), Phase-Normalizer, Login-Popup-
Resolver, Lock-Keeper/Stale-Politik, Marker-/Idle-Gate-Matrix der drei Tasks.
README: `scripts/`-Sektion mit Einzeiler je Skript + Verweis hierher.

**DoD:** Markdown-Links/Codeblöcke intakt; keine erfundenen Flags (aus
`--help`-Quellen ableiten).

### A7 / T58 — Review-Fix-Batch (Subagent-Review liegt vor)
> **Voller, frame- (+live-)verifizierter Report: `docs/reviews/2026-11-03-scripts-review.md`**
> (27 k, mit Beweisen; erklärt u. a. den Live-Ausfall „arena lobby did not open").
> Nach A1 ziehen, damit jeder Fix durch die Regressionstests abgesichert wird.
> Branch `feature/T58-review-fixes`. 1 Finding = 1 Commit mit Finding-Nr.

**A7a — HIGH (zuerst):**
1. `afk_arena.confirm_dialog`-Probes sitzen ~50 px unter den echten Knöpfen —
   der Nie-Diamanten-Kauf-Gate feuert nie (Cancel-Tap 1014,784 trifft nichts).
   Ground-Truth: X ~(1010,728), grün ~(1142,734); stage_push-Koords
   (1014,710)/(1155,710) evaluieren auf denselben Frames korrekt → EINEN
   Detector in afk_claim_vision bauen, beide Skripte nutzen ihn.
2. `afk_claim_vision.is_battle_modes` False-Positive auf hellen Welt-Frames →
   open_battle_modes öffnet nichts, arena tippt blind (Live-Ursache!). Fix:
   Welt ausschließen (z. B. AFK-Chip (60,1036) < 100).
3. `afk_hero_level.read_level`: `Lv.74986`→749, `LvL99`/`LV.74`→None;
   is_detail zu lose (Hall passiert); key(4) verlässt den Hall ohne
   Re-Navigation; Exit 0 trotz Totalausfall. Fix: case-insensitiv +
   Plausibilitäts-Guard + Hall-Re-Verify (972,1034) + Exit 1.
4. `afk-wall-dash`: Crash bei non-dict-JSONL/None/String-Nulls (load + STATE);
   Reason-Familien werden nie gematcht (Stats = 0). Fix: isinstance-Guards,
   fmt_int-Helper, `'defeat' in reason`-Familien; STATE ist tot → aus letztem
   Event mit stage/power ableiten; ts ISO-Parsing.
5. `afk_arena` Exit-Codes: beide Abbruchpfade returnen 0 → watch.sh verbrennt
   den Tagesmarker bei Fehlschlag. Fix: ok-Flag; return 1 wenn wins==0 und
   kein exhaust-Pfad; Tap-rc wie v.tap behandeln.
6. Ops: `.spectre`-Prune (1,3 GB, 104 ungeprüfte shot-Dirs → die 30 neuesten
   behalten) + `idle_seconds` c_long-Overflow (nach ~24,8 Tagen Windows-Uptime
   wird idle negativ → ALLE Scheduled-Runs SKIPpen). Fix: GetTickCount.restype
   uint32 + (tick-dwTime)&0xFFFFFFFF; Prune im claim_vision-Start.

**A7b — MED:** classify-POPUP/WORLD-1-Punkt-Klippe (d=-9 real; drittes
tell oder UNKNOWN statt Blind-Tap); dailies: ARGS-Global nur in __main__
(run_dailies(args) übergeben), quick_claim-Tab-Fehler → BACK + Panel-Re-Open,
open_menu-Retries statt Abbruch; gift: Entry-Tap-Retry + Panel-Check-Retry,
not-found → WARN-Exitcode statt 0; hero_level: x10-Nachschlag + erneutes
Lesen statt Einzel-Unverändert=Abbruch, letzten Level zurückgeben; dailies-
ChestClaim auf gemeinsame claim_vision-Funktion; arena Tap-Retry.

**A7c — LOW:** swipe-rc prüfen, save_power_state atomar (tmp+replace),
dismiss-Taps classify-gaten, per-pid shot-Dirs auch in hero_level/gift,
off-screen-Swipes clampen, `_level_hands` löschen (→ A4), tote Imports/Branches
entfernen (arena reach_world/at_world, dailies TMP, gift struct).

### A8 / T60 — Runtime-Fix-Batch (Review afk_stage_push + afk_dream_realm)
> **Voller Report: `docs/reviews/2026-11-03-runtime-review.md`** (artefakt-
> verifiziert inkl. reproduziertem Pre-Fight-Timeout; Frames + Messwerte als
Claude-Batch nach A1, 1 Finding = 1 Commit, Branch `feature/T60-runtime-fixes`.
(A8 zog als T60 um — T59 ist der spectre-mcp.)

**A8a — HIGH:**
1. `afk_dream_realm.start_fight` akzeptiert uniform-schwarze Übergangs-Frames
   als „Kampf läuft" → 153 s Pre-Fight-Stand, Timeout, Chance verloren
   (shots-33128 vs. shots-1752). Fix: positiver Fight-Marker (Profil aus
   shots-1752: (960,1040) weder weiß noch grün; lum((1280,1010))<120) —
   dunkle Frames weiter pollen, nie „läuft" annehmen.
2. `wait_for_fight_end`: kein Ready-Screen-Re-Arm → nach ≥3 is_ready-Frames
   ohne Fight-Marker einmal PREP/BOSS re-tappen und weiter pollen.

**A8b — MED:** stage_push LAUNCHER/LOADING-Kreuzklassifikation (Live-Fights →
„game crashed" exit 3; dunkle Nacht-Fights → LOADING/unknown-strike; Gate
verschärfen bzw. nach BATTLE prüfen, LOADING = „keine Info"); dream
`_dim_probes` matcht Transitionen → falsches „fight ended" (Debounce/
lum<40-Ausschluss); `back_to_ready` 4-Unknown-Toleranz vs. 90-s-Fight;
2x-Tap auf Fight-Marker gaten; Chance-Bookkeeping per OCR („Chances: N/7",
Fight nur bei Marker zählen); globaler Prune (dream realmt nie; tote Dirs;
Call in beiden mains + im Loop); stage_push stale-RESULT-Phantom-Win;
PREP-Debounce nur bei „st2 immer noch PREP" als Wand werten; einheitliches
try_shot (kein FATAL mid-chain, Backoff, adb-Exit 2 nach ~5 Fails);
Popup-Fallback (OCR 'Level/Perk/Tap to close' → Close (960,540), Strike-Reset).

**A8c — LOW:** reach_world-Unknown-Poll; HERO_PROBE-Marge (171 vs 170 → ≥180
oder Punkt verschieben); toter doppelter POPUP-Check; Summary-Close (960,1000)
→ (960,540); parse_power aufwärts + Anchor `^Battle\b`; wall_report-Fehler
erhalten (log_error) + OCR-Erstaufruf-Warmup (30 s).

---

## 2. Wave B — Recon (Hermes) → Code (Claude) → Live-Verify (Hermes)

> Jeder B-Task wird erst akut, wenn der RECON-Block gefüllt ist. Hermes füllt
> ihn beim nächsten Live-Fenster (Gerät ist wieder online). Format des
> RECON-Blocks: Screen-Folge, exakte Koords, Probes, Edge-Cases, was NICHT
> angetippt werden darf (Kauf-Risiko).

### B1 / T52 — Dura's Trials Driver (Fail = Refund → Retry bis Sieg)
**RECON (Hermes):** Einstieg/Modus-Ort, Floor-Screen, Challenge-Koord, Token-
Anzeige, Post-Loss-/Post-Win-Folge, Tagesrotation-Hinweis.
**CODE (Claude):** `scripts/afk_durability.py` im Muster von
`afk_dream_realm.py` (state-gated, kein Blind-Tap, Ressourcen-Stopp).
**LIVE (Hermes):** 2 Läufe verifizieren; erst dann in den Daily-Wrapper.

### B2 / T53 — Dream Realm: Tier-Navigation + Skip
**RECON (Hermes):** Tier-Umschalter auf der Boss-Page (Pfeile/Tabs?), zweite
Boss-Page (Snow Stomper) verifizieren; Skip-Verhalten auf der Prep (instant?),
Side-Effects auf die Damage-Wertung.
**CODE (Claude):** `afk_dream_realm.py` erweitern: Tier-Schleife (alle Tiers
mit Chance>0), Skip optional per Flag.
**LIVE (Hermes):** verifizieren, `--fights`-Semantik dokumentieren.

### B3 / T54 — Arena: Victory-Card-Dismiss + Mehrfach-Kette
**RECON (Hermes):** Victory-Karte nach Arena-Kampf (Position Dismiss), Verhalten
„Challenge!"-Rückkehr, Abbruchkriterien (Purchase-Dialog, 0 Versuche).
**CODE (Claude):** `afk_arena.py --fights N` mit Karten-Dismiss zwischen den
Kämpfen (statt N Einzel-Invocations), gleiche Gates.
**LIVE (Hermes):** 1× N=4 durchlaufen.

### B4 / T55 — Friends-Favors + Homestead-Assists
**RECON (Hermes):** Friends-UI (Favors x10 → Chest), Homestead-Besuch/-Assist,
Tages-Cap-Anzeigen, „schon erledigt"-Marker-Erkennung.
**CODE (Claude):** `scripts/afk_social.py` (Friends + Assists, Marker-Files).
**LIVE (Hermes):** 1 Lauf; dann in Daily-Run (einmal täglich, Marker).

### B5 / T56 — Season-Banner-Detektor (für T45j-Arbitrage)
**RECON (Hermes):** Ort des Season-Banners/„Time Left"-Texts (Monthly-Popup
hatte „Time Left: 23d"; Season-Banner suchen), OCR-Proben.
**CODE (Claude):** `scripts/afk_season.py`: OCR → `season-state.json`
{time_left_hours, captured_at}; keine Taps (reiner Detektor) + Decision-Text
(HOLD ab ≤6h etc.) für den Scheduler.
**LIVE (Hermes):** Probe gegen aktuellen Banner.

### B6 / T57 — Legend Trial Sonntags-Runner (T45f)
**RECON (Hermes):** Turm-Auswahl (Light/Nature/Eternity/Will), Sonntags-Status
„alle offen", Key-Zähler, Challenge-Flow. **Policy:** verbraucht Keys (T29).
**CODE (Claude):** `scripts/afk_legend_trial.py` mit `--towers all|<Name>`,
Key-Gate `--use-keys`.
**LIVE (Hermes):** Sonntags-Lauf (bzw. kraft Plan-Tag).

---

## 3. Wave C — nur Hermes (Live/Politik/Ops)

- C1: Queue-Driver weiterlaufen lassen; P8-Rest (R9 = A4), T44-Finish.
- C2: `afk_hero_level.py` in den Daily-Run verdrahten (Marker `level-last.txt`,
  Ressourcen-Stopp ist eingebaut) — Policy-Anzeige im Log (Gold/EXP vor/nach).
- C3: Night-Task-Live-Verifikation (nächste Nacht 02:00), Wall-Report prüfen.
- C4: Recon-Blöcke B1–B6 füllen (Live-Fenster, Gerät sauber parken).
- C5: 2×/Woche `spectre-walls.html` rendern + Bot-Log-Kurzcheck.

---

## 4. Übergabe-Workflow (so füttert man Claude)

1. Immer **Gemeinsamer-Kontext-Block** (CLAUDE-TASKS.md, Kopf) + EIN Brief
   (z. B. A1) in eine Claude-Code-Session. Nicht mehrere Briefs auf einmal.
2. Claude arbeitet auf `feature/T46-...`; Commit lokal.
3. Hermes: Review-Fresh-Eyes (Cheap-Model-Subagent, minimaler Kontext),
   merge `--ff-only` oder cherry-pick, `main` bleibt grün.
4. Wenn Claude bei einem Brief blockt: Fallback-Tabelle anwenden; wenn der
   Trick nicht greift → Hermes baut den Task, Claude zieht den nächsten.

> Dieser Plan ist bewusst als Datei im Repo (`docs/claude-wave-2-plan.md`) —
> Claude Code liest ihn direkt als Kontext statt Kopier-Rauschen.

---

## 5. Hermes-Zusatz (03.11., nach Plan-Freeze)

- **T59 (Brief in `CLAUDE-TASKS.md`; Branch `feature/T59-spectre-mcp`):** `spectre-mcp` —
  stdio-MCP-Server, der Agenten die Live-Pipeline als Tools gibt (find/regions/dump/
  hot/hunt/search/read/adb_taps; EINZIGER adb-Owner). Registrierung via `.mcp.json`;
  Live-Smoke durch Hermes nach Merge.
- **STATUS 03.11.: T59 gebaut (`13e959f`), unabhängig verifiziert (11 Tests grün, clippy 0 Warnings, Live-Smoke health/find/regions/read/screencap gegen BlueStacks ok), in `main` gemergt und Branch gepusht. Fresh-Eyes-Review (12 Findings) eingearbeitet: `0fe3bcd` (Config/Docs) + `d4c6ce6` (ensure-Härtung; Launch via MSYS-EXCL live verifiziert). Topologie-Punkt (main noch ohne Docs) löst der Wave-Merge; Exe für `.mcp.json` liegt bereit.**
- **`scripts/bluestacks-ensure.sh`:** prüft/startet BlueStacks idle-gated (Exit 4 =
  Idle-Gate). Queue-Driver nutzt es bei fehlendem Device statt "Sergej startet manuell".
- **Agent-Docs:** `CLAUDE.md`, `AGENTS.md`, `docs/agent-workflow.md`,
  `.claude/settings.json` (Model-Pin), `.mcp.json` (projekt-scope).
