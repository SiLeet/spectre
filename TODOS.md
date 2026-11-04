# Spectre — TODO & Parallel Work Plan

> **Parallel-Strategie:** Hermes + Claude Code arbeiten gleichzeitig.
> Jeder Task ist so geschnitten, dass er **disjunkte Dateien/Crates** berührt,
> damit parallele Arbeit ohne Merge-Konflikte läuft.
>
> **Definition of Done (für ALLE Tasks):**
> - `cargo check --workspace` = 0 errors
> - `cargo test --workspace` = alle Tests grün (neue Tests für neue Logik)
> - `cargo clippy --workspace --all-targets` = 0 warnings
> - Commit + Push auf `main`, CI grün

---

## Status-Legende

- ⬜ Todo · 🟦 In Arbeit · ✅ Done · ⏸️ Blocked

---

## P0 — Kern-Features

### ✅ T1: Web-Dashboard (`spectre serve`) — erledigt 2026-10-31 (#10)
- **Berührt:** neues Crate `spectre-web/` (nur) + optional `spectre-cli` Subcommand `serve`
- **Ziel:** Live-Web-UI im Browser: Prozessliste, Memory-Regionen, Werte-Lese-Helper, Scan-Ergebnisse, Bot-Log.
- **Vorschlag:** Axum/Actix + minimales HTML/JS, `spectre serve --port 8787`.
- **DoD:** `spectre serve` startet, Browser zeigt Prozessliste + `read_u32`-Probe von einem PID; Tests für die HTTP-Handler; CI baut das neue Crate.

### ✅ T2 (DONE, PR #1): Native Windows-Input-Simulation
- `spectre-bot/src/wininput.rs` — WindowsInput via SendInput; 4 Tests
- Merged + CI grün.

### ✅ T3 (DONE, PR #2): Offline-Dump-Diff
- `spectre-core/src/diff.rs` + CLI `dumpdiff`; 14 Tests
- Live verifiziert (Änderung bei 0x4 erkannt). Merged + CI grün.

### ✅ T4: Pointer-Ketten (`spectre chain`) — erledigt 2026-10-31 (#8)
- `resolve_ptr_chain` existiert in core; CLI `chain` siehe T4-Brief (bei Bedarf ergänzen).

---

## P1 — Verbesserungen & Docs

### ✅ T5 (DONE, PR #6): CLI-Referenz-Doku
- `docs/cli-reference.md` (417 Zeilen). Merged + CI grün.

### ✅ T6 (DONE, PR #3): Lua-API erweitern
- `spectre.read_fields()` + `spectre.regions()`; 8 Sandbox-Tests. Merged + CI grün.

### ✅ T7 (DONE, PR #4): Cron-Scheduling im Bot
- `schedule: "0 */6 * * *"` via chrono; 38 bot-Tests. Merged + CI grün.

### ✅ T8: Challenge-Repo / Quickstart — erledigt 2026-10-31 (#9)
- `examples/` erweitern, `docs/` (nur).

---

## P2 — Ausblick

### ✅ T9: Web-Härtung — erledigt 2026-10-31 (#11)
### ✅ T10: Multi-Emulator-Orchestrierung
- `spectre-adb/src/multi.rs` — AdbManager + parse_adb_devices; 10 adb-Tests. Merged + CI grün.

---

## P3 — Live-Offset-Discovery (AFK Journey) — läuft seit 2026-10-31

### 🟦 T11: AdbReader live gegen AFK Journey (BlueStacks)
- ✅ Prozess finden, 4200+ Regionen lesen, u32-Scan, Dumps (4K-Block-Reads, ~3.3 MB/s)
- ✅ `spectre hunt <pid> <min> <max>` (neues CLI-Feature, Commit `3e742dd`)
- ✅ Gold-Kandidat 259850 identifiziert — ABER: nach Gold-Erhalt durch Belohnung **unverändert**
  → war NICHT der echte Gold-Wert. Die echte Adresse muss per Aktion-Diff bestätigt werden
  (kurzer Zeitabstand! 1h-Diff = 244k Churn-Slots, unbrauchbar).
- ⏸️ **NÄCHSTER SCHRITT:** Im Town-Screen Gold-Wert OCR-lesen → exakte Zahl in frischem
  Nachher-Dump suchen → Adresse in `games/afk-journey/offsets.yaml` eintragen.
- 📌 User-Hinweis: **Memory-first statt Pixel** (docs/memory-first.md) — UI-State-Offset
  finden (Town ↔ Open World Wechsel + dumpdiff), dann Navigation per Memory.
- ✅ **hot-Scan Root-Cause gefunden + gefixt** (Commits `b56f897` + `97b32ee`): toybox `grep -bo`
  liefert pro Zeile nur EINEN Offset → `tr` machte alles einzeilig → `end`-Sentinel verloren →
  „no memory readable" trotz lesbarem Speicher. Fix: `od -w256 | sed "s/^ //"` + `grep -bF`
  (ein Offset pro Zeile), Parser scannt Zeileninhalt byte-aligned. **Zweiter Teil-Bug:** `sed 's/^ //'`
  mit Single-Quotes im Rust-Code brach das `su -c '...'`-Quoting → Double-Quotes (`97b32ee`).
- ✅ **LIVE-BEWEIS (`97b32ee` + `b60401f`)**: 16-Seiten-Scan des Spiel-Heap für Muster `0a f7 03 00` (259850)
  über die echte Geräte-Pipeline → errechnet exakt **0x724DF000A578** (bekannte Team-Power-Adresse!).
  **FULL-SCAN**: `spectre hot 7529 0af70300 --adb --limit 3` → 3 Treffer, alle per Direkt-Read
  verifiziert (u32 = 259850): 0x724D63FBD624, 0x724D6E4A1CE4, 0x724D70AD6FE0. `spectre hot` ist
  damit END-TO-END live verifiziert (vorher: "no memory readable" trotz lesbarem Speicher).
  25 adb-Tests grün. ⚠️ Rest-Trade-off: Muster über 256er-Zeilengrenze unsichtbar (~0.4-1.2%,
  Recheck per dump). Volle Scan-Läufe dauern Minuten (Performance: alle >GB Regionen über ADB).

### ✅ T12: Game-Orientierung + Übergabe
- docs/afk-journey-guide.md (Screens, Währungen, sichere Trigger-Aktionen), docs/memory-first.md.
- TODOS.md + CLAUDE-TASKS.md als Übergabe für parallele Claude-Arbeit.

### ✅ T13: On-device Hot-Scan (`spectre hot`) — live gefixt 2026-10-31 (Commit `b56f897`)
- xxd+grep auf dem Gerät, nur Treffer über adb; byte-aligned, Chunk-Overlap.
- ⚠️ War ursprünglich „Done" markiert, lief aber live nie: toybox-`xxd` ignoriert `-c1`
  (`f3adde9`), dann toybox-`grep -bo`-Einzeloffset-Bug (`b56f897`). Jetzt live-fähig.
### ✅ T14: Range-Suche (`search --min/--max`) — erledigt 2026-10-31 (#15)
### ✅ T15: `spectre offsets` + Validator — erledigt 2026-10-31 (#16)
### ✅ T16: AFK-Beispiel-Bots (examples/bot-config-afk.yaml, safe_claim) — erledigt 2026-10-31 (#17)
### ✅ T17: Native Linux-Reader (pread auf /proc/<pid>/mem) — erledigt 2026-10-31 (#18)
---
## P4 — Für Claude (neu, 2026-11-01, ohne Live-Gerät machbar)
- ✅ **T18: v0.4.0-Release vorbereiten** (2026-10-31, Tag v0.4.0 setzt Hermes nach CI) — Version-Bump + CHANGELOG für
  hunt/hot/offsets/range-search (Tag wird von Hermes gesetzt). Brief in CLAUDE-TASKS.md.
- ✅ **T19 (#19, 43999b2): Bot-Loop ehrt Task-Config** — schedule > interval > default pro Task,
  Task-Kopf-Bedingungen. Brief in CLAUDE-TASKS.md.
- ✅ **T20 (#20, 8a7deee): CLI-Referenz + README auf hunt/hot/offsets/range-search** aktualisieren.
  Brief in CLAUDE-TASKS.md.
### ✅ T21: Live-Bot-Claim verifiziert (2026-10-31, PR #22 / f828677)
- **Bugfix:** `CliInputSimulator` löste die adb-Serial nicht auf → alle Taps scheiterten an
  „more than one device/emulator" (Reader verbindet `127.0.0.1:5555` neu, BlueStacks listet
  zusätzlich `emulator-5554`). Fix: Serial aus `adb devices` auflösen (eindeutig → nehmen;
  mehrere → `host:port`-Eintrag bevorzugen), `-s <serial>` an `adb shell input` übergeben.
- **Verifizierte AFK-Claim-Sequenz** (echte Taps): Leerraum (300,250) → AFK-Progress (70,1032)
  → Truhe (975,760) → Claim (960,602) → Back (474,1010). Beweis: AFK-Timer 05:38:40 → 00:00:02.
- **Live-Loop:** `spectre bot examples/bot-config-afk-live.yaml --adb` (Test-Intervall 60 s)
  → 3 Claims in 3 Minuten, 0 Warnings; Timer danach 00:01:30. Memory-Guard `team_power`
  (259850 = HUD „259K") bei jedem Tick grün.
- `examples/bot-config-afk-live.yaml` nutzt die echte Sequenz (Intervall 15 min);
  stale `afk_pool_*`-Checks entfernt (Heap-Layout verschoben, nur team_power stabil).

### 🟦 T11 (Fortsetzung): Gold-Offset — Claim-Mechanik nutzbar, Wallet weiter offen
- AFK-Truhe liefert **+20743 Gold/h** (Popup), Claim ändert den Timer (verifiziert).
- **Ausgeschlossen (2026-10-31):** Wallet/AFK-Pool liegen NICHT in den ersten 8 MB des
  Hot-Heaps (0x724DF0000000) und NICHT in den 6 großen rw-Heaps
  (0x724dd04e7000 69 MB, 0x724ddff1d000 72 MB, 0x724e30000000 52 MB, 0x724e60000000 68 MB,
  0x724ea0000000 148 MB, 0x724eb0000000 64 MB) — geprüft als u32/u64 **und** f32/f64 mit
  Zwei-Runden-Delta-Schnitt (Claims nach 266 s bzw. 517 s Akkrual, Rate 5,76/s).
  Ein reiner Erwartungswert „Rate × Zeit" trifft also nicht — der Claim grantet offenbar
  nicht 1:1 die angezeigte Stundenrate in einen einzelnen Slot.
- **Wichtige UI-Falle:** Der Goldwert im Helden-Detail-Screen (z. B. „11 613", „8181") ist ein
  **Level-Up-Preis**, keine Balance — er ändert sich nach einem 117k-Claim nicht.
  Shops zeigen eigene Währungen (Recruit-Tickets 1 260, Diamanten 31 920), nie Gold.
- **Nächster Schritt:** Gold-Balance aus dem Town-Hub-HUD lesen (oberste Leiste unter Team-Power;
  im Homestead/Open-World-HUD steht dort nur Event-Währung) → exakten Wert hot-suchen →
  Claim → Slot bestätigen. Tooling dafür liegt in `scripts/gold-hunt.sh` + `scripts/gold-analyze.py`
  (3-Zeitpunkt-Dump A/B/C über die großen Heaps, Wallet-Kriterium A≠B, B==C, stabil im Idle).

### ❌ T23: Wallet-Hunt vollständig negativ (2026-10-31) — Gold ist clientseitig nicht auffindbar
- **Letzter, erschöpfender Versuch** (`scripts/wallet-hunt-all.py`): ALLE 625 noch nicht
  abgedeckten anonymen rw-Regionen (535 MB) plus die bereits geprüften Bereiche ≈ 1 GB,
  drei Zeitpunkte A (idle) → Claim → B (sofort) → 90 s → C, **modellfrei** (kein Rate×Zeit):
  Kriterium A≠B, B==C, B>A, 200 ≤ Δ ≤ 20 000, Wert 500..50 Mio.
- Ergebnis: 377 631 Rohtreffer, nach Float-Filter und Gruppenbildung **nur Alloc-Muster**
  (0→4096, 0→8192, 1→16385 …) — kein Wallet-Kandidat, auch nicht als Kopie-Gruppe.
- Ebenfalls negativ: AFK-Zeit als Sekundenzähler (Δ=+25 s exakt), als Epoch, big-endian,
  f32/f64; AFK-Raten (20743/56170/1529) in allen großen Heaps; Raten im offenen Popup.
- **Schlussfolgerung:** Gold ist server-autoritativ; der Client hält den Wert offenbar nur
  transient (Netzwerkpuffer beim Öffnen des Panels) oder gar nicht. Ein Offset dafür ist mit
  Read-only-Tools **nicht** zu pinnen. Konsequenz: Der Bot bleibt bei `team_power` als Guard;
  Gold-Guards sind nur über UI-Feedback möglich (Screenshot/Popup), nicht über Memory.
- **Nicht weiter verfolgen**, außer mit einem anderen Ansatz (z. B. Netzwerk-Traffic,
  Hook auf die UI-Bindung oder Server-API).

### 🟦 T22: ui_state-Offset (Panel offen vs. Welt) — Methode gescheitert, Heuristik bleibt
- Ziel: Claim im Bot verifizierbar machen (statt Reset-Tap-Heuristik).
- Versuch 1: 4-Zustands-Schnitt W1/P1/W2/P2 über die ersten 4 MB des Hot-Heaps
  (`scripts/ui-state-hunt.sh`) → 163 u32-Kandidaten (W1==W2, P1==P2, W!=P, Wert ≤255).
- Versuch 2: Live-Nachprüfung der 6 besten Kandidaten (`scripts/ui-state-verify.sh`,
  je 2× Welt / 2× Panel) → **alle gefallen**: Werte sind Pointer/Rauschen, kein 0/1-Flip.
- Lehre: Der Hot-Heap churnt so stark, dass Whole-Heap-Diffs auf dieser Basis keine
  stabilen State-Slots liefern; jeder Kandidat MUSS live in beiden Zuständen
  nachgelesen werden, sonst pflanzt man Zufallstreffer in die Config.
- Bot bleibt bei: 2× Back + Leerraum-Tap vor der Sequenz (verifiziert aus AFK-Panel,
  Resonating Hall und Hero-Detail). Falls ui_state später gebraucht wird: Kandidaten
  über deutlich mehr Zyklen (≥6) UND nur Slots, die in beiden Zuständen über Minuten
  stabil sind, plus Live-Probe.

### ✅ T24: Bot produktiv — Scheduler live, Daily-Gift automatisiert (2026-10-31)
- **Windows Task `Spectre AFK Bot`** (15-Minuten-Takt, nur interaktiv) ruft
  `scripts/afk-bot-watch.sh --scheduled` auf. Live bestätigt: 32 Läufe / 27
  verifizierte Claims im Log, Läufe feuern pünktlich alle 15 min.
- **Idle-Gate**: `--min-idle` via `GetLastInputInfo` — SKIP (exit 5), wenn der PC
  in Benutzung ist (live: 114 s < 180 s → SKIP). Der Bot übernimmt den Screen
  nie, während Sergej spielt oder arbeitet.
- **Lock**: `.spectre/afk-bot.lock` serialisiert konkurrierende Läufe (exit 6,
  stale nach 3 min) — nötig, weil geplante und manuelle Läufe sich ansonsten
  in die Tap-Sequenz greifen (live erlebt).
- **Daily Journey's Gift** (`scripts/afk-daily-gift.py`): öffnet Login Rewards
  (schwebt in der Welt → Kamera-Pan-Suche mit Orange-Probe), tippt nur Zeilen
  mit grünem Badge (G−R>40 = geclaimed + heute; Zukunfts-Tage grau, werden nie
  angetippt → kein Kauf-Risiko aus den Event-Tabs), dismissed „Rewards Obtained"
  und die Item-Info-Tooltips geclaimter Zeilen. Live: Day 3 geclaimt
  („Rewards Obtained", 10 Briefe); No-Op-Pfad verifiziert.
- **Wichtiges UI-Faktum:** Der Login-Rewards-Eintrag **verschwindet**, sobald die
  Tagesbelohnung geholt ist — fehlender Button = „heute schon geclaimt" (exit 0).
- `--scheduled` läuft das Daily-Gift einmal pro Tag nach dem ersten erfolgreichen
  Chest-Claim (Marker `.spectre/daily-gift-last.txt`).

## Bonus (Claude)

### ✅ Release-Workflow (PR #7)
 - GitHub Actions Release-Job baut `spectre.exe` und publisht Release v0.2.0. Merged + CI grün.

---

## Wie zusammenarbeiten (Hermes + Claude Code)

1. **Hermes** koordiniert: hält `main` grün, reviewed & merged.
2. **Claude Code** arbeitet an einem Task in einem **eigenen Branch/worktree**:
   ```bash
   git checkout -b feature/T1-dashboard
   ```
3. Jeder Task-PR wird von Hermes gegengecheckt (Build + Tests + Clippy), dann gemergt.
4. **Konfliktvermeidung:** Tasks berühren unterschiedliche Crates — siehe „Berührt".

> Canonical-Datei: `TODOS.md` — beim Abschluss eines Tasks Status + Datum aktualisieren.
## P5 — Dailies-Roadmap (Queue, 2026-10-31)
> Queue-Discipline: neue Wünsche/Corrections werden hier ANGEHÄNGT, nicht vorgezogen.
> Bearbeitet wird sequenziell von oben; Stop erst bei 100 % cleared.

- ✅ T25: Dailies-Runner (`scripts/afk_dailies.py`) — Chest-Claim + Quests (3 Tabs
  Quick Claim) + Mail (Read All), alle state-gated. Live: 10 Diamonds + 2K Gold
  + 60 XP aus Quests, 100 Diamonds + 20K Gold aus Mail.
- ✅ T26: Scheduler integriert Daily-Gift + Dailies-Runner (Marker-Files).
- ✅ T27: Arena-Flow — Live kartiert + `afk_arena.py` (schwachster Gegner via
  Kampfkraft-Sortierung, 2 Kämpfe). Danach: Versuche aufgebraucht (5/5), das
  Spiel bot einen **Diamanten-Kauf** („Warrior's Guarantee x1") — erkannt,
  CANCELLED und Run gestoppt (T36-Kategorie: Kauf-Risiko). Daily fertig.
- ✅ T28: Dream Realm (7/7) — Flow automatisiert + live verifiziert (2026-11-01, 09f3e41).
  `scripts/afk_dream_realm.py` läuft 2/2 Kämpfe sauber (Chances 7/7 → 4/7,
  Highest Damage 99.2 % / 1,807,104), Exit in WORLD. Kern-Erkenntnisse: der
  Elite-Challenge-Kampf ist ein ~90 s Damage-Race (kein Win/Lose) — alter Code
  wartete nur 75 s und las den laufenden Kampf als Niederlage; Prep-Battle-
  Button sitzt bei (1280,1010), (960,1010) ist dort der SKIP-Button (nie
  antippen). Endzustand ist eine helle „BATTLE ENDED“-Karte (orangefarbener
  Banner, „Tap to close“ unten mitte), keine dim Popup-Sequence; danach ggf.
  Rewards-Popup/Hero-Card. State-Probes statt OCR, keine Blind-Taps bei
  unbekannten Frames. Chances verbrauchen sich wie Arena-Versuche (Daily).
- ✅ T38: Review-Fix-Batch für `afk_dream_realm.py` (Subagent-Review zu 09f3e41,
  12 Befunde) — eingezogen + live verifiziert (2026-11-01, 1/1 Kampf sauber:
  Boss → Prep → ~90 s Fight → Battle-Ended-Card → Exit WORLD, Exit 0).
  1. [HIGH] is_boss_page/is_prep ZWEISEITIG — aber datenbasiert korrigiert:
     Die Boss-Page-Battle-Fläche ist eine VOLLBREITE grüne Leiste (Boss-Probe
     (960,1040) UND Prep-Probe (1280,1010) beide grün); Prep hat rechts grün
     + WEISSE SKIP-Fläche Mitte (960,1040)=(248,244,238). Regel: Boss = beide
     grün, Prep = nur rechts grün. Naive "nicht-grün-Exclusion" tötete beide
     Prädikate (Live-Lauf flog auf, shots-28532).
  2. [HIGH] is_dim_popup nicht mehr Lum<25: kalibriert auf echte Shots —
     Dim-Overlay = Back-Pfeil <25 UND Bottom-Bar (890,1060) <25 UND Corner-
     Glow 30..100 (echte Popups: 4-10/5-8/58-69). Kampf-Frames (137/42),
     Boss-Page (228), Nacht-Welt (47, hell) und schwarze Lade-Frames (0/0/0)
     matchen NICHT. Plus 2-Shot-Debounce (dim_confirmed) vor jedem Dismiss.
  3. [MED] reach_world(): bei classify==UNKNOWN Abbruch statt Blind-BACK.
  4. [MED] RuntimeError aus v.tap/v.shot → try/except in main → Exit 2.
  5. [MED] is_hero_card: zweite Probe (1450,850)>150 + Hero-Probe >170
     (statt single >180, das an PANEL~178 grenzte).
  6. [MED] start_fight(): nach Battle-Tap wird gewartet, bis der getappte
     Ready-State verlassen ist (6 Shots × 2.5 s) — kein Re-Tap in den
     Kampf-Start-Übergang; Ready↔Ready-Wechsel (Boss→Prep) wird gefolgt.
  7. [MED] enter_dream(): Battle-Modes-Menü wird per is_battle_modes-Probe
     verifiziert, erst dann DREAM_CARD (2 Versuche).
  8. [MED] afk_claim_vision: CLAIM-Popup persistiert → 1 Retry, danach
     Exit 1 statt stiller Exit 0. ⚠️ DABEI GEUNDEN: afk_claim_vision.py war
     seit Commit 40de5f4 (00:37) SYNTAKTISCH KAPUTT (Docstring Zeile 144,
     fehlendes `"` → unterminated triple-quoted string) — JEDE Ausführung
     des Vision-Moduls (Dream Realm, Dailies, Arena) und jeder Scheduler-
     Lauf seit 23:37Z crashte mit SyntaxError. Fix eingezogen; Logs
     (.spectre/logs/afk-bot-2026-10-31.log) belegen die Crash-Kette.
  9. [LOW] wait_for_fight_end prüft auch den letzten Shot nach Deadline.
  10. [LOW] --dry-run führt jetzt echte Probes aus (dr_start + alle
      Prädikate) statt No-Op.
  11. [LOW] DIM_DISMISS (480,300) bleibt, aber mit Verifikation: persistiert
      das Dim-Popup → BACK, danach Abbruch statt Blind-Taps.
  12. [LOW] globaler Dismiss-Budget (_dismiss_taps, MAX 24) über alle
      Retry-Loops; Überschreitung = sauberer Abbruch.
- 🟦 T34-Hinweis (Queue-Driver, 01:0x): Paralleler Writer arbeitet unver-
  committet an `afk_stage_push.py` (Skip-Button-Auto-Battle-Loop, T34-Thema).
  Queue-Driver fasst T34/die Datei in diesem Lauf NICHT an (Kollisionsgefahr);
  T34 bleibt offen und wird bearbeitet, sobald die Änderungen committed sind.
- ⏸️ T29: Legend Trial / Arcane Labyrinth / Honor Duel — BLOCKIERT (Entry-
  Currencies): Legend Trial/Labyrinth verbrauchen Keys ×3 (T29-Update unten),
  **Honor Duel verbraucht 1 Duel-Ticket pro „Play Now"** (Vermessung 01:2x:
  Mode-Screen = Total Points (Unranked) 100, 5 Tickets oben rechts, „Play
  Now" (1032,996) mit x1-Kosten-Badge, „Participate to get Lucky Keys!",
  Ranking/Records-Buttons rechts oben — NICHT gespielt). Exploration damit
  abgeschlossen; Freigabe nur durch Sergej (wie T33/T35).
- ✅ T30: Homestead-Ernte — geschlossen (YAGNI, siehe ✅-Abschnitt unten: nichts zu automatisieren).
- ✅ T31: Mail/Quest-Reminder — bereits implementiert (Marker-File, siehe ✅-Abschnitt unten).
- ✅ T32: Skill-Hygiene — erledigt (Auslagerung in references/, siehe ✅-Abschnitt unten).
- ⏸️ T33: Helden-Upgrades (Level-Automatik) — BLOCKIERT auf Sergejs Ressourcen-
  Regel (Vorschlag: nur Team-Helden, Gold < 20 % Bestand, max 10 Level/Lauf).
- ✅ T34: Stage-Push --auto + x2-Speed — bereits implementiert + integriert:
  `afk_stage_push.py` hat `--auto` (Auto-Battle-Loop mit Skip-Button-Resolve)
  und tippt SPEED_X2_BTN (1160,855) beim Auto-Start (x4 premium-locked, wird
  nie angetippt). Der Scheduler (T39, dd4ed3e) ruft es im Daily-Run mit
  `--auto --auto-minutes 6` auf; das alte „Idle-Fenster"-Konzept ist durch
  die festen Runs (05:10/17:10) abgelöst. Live 01:2x: DEFEAT-Pfad verifiziert
  (Wand erreicht → Exit 0, keine Blind-Taps); der x2-Tap war Teil der
  verifizierten T39-Push-Kette (Stage 218→249). Restliche Integration in den
  Progress-Run = T40 (P6).
- ⏸️ T35: ×4-Speed: nur falls Sergej Premium kauft (Button gesperrt — Shop-
  Risiko); vorher nicht anfassen.
  ⏸️ Queue-Driver 21:08 CET: Policy-Blocker bestätigt — Premium-Kauf ist
  nicht freigegeben; den gesperrten ×4-Button deshalb nicht antippen.

### 🟦 T27 (Teilstand): Arena-Flow kartiert — Skript folgt
Verifizierte Koordinaten/Sequenz (19:0x Uhr, 2 Kämpfe live):
1. Battle Modes (890,1060) → Arena-Karte (1200,300) → Lobby (Rang Novice III,
   Tokens oben rechts 1200 + Versuche "4").
2. Challenge (1080,1004) → Select Opponent: 3 Gegner, Fight-Buttons links
   (760,870) / Mitte (980,830) / rechts (1160,750); Schwächsten nehmen (Power
   1150 < 1250 < 1365). Ganze Karte antippen (750,500) startet auch.
3. Kampf läuft automatisch (unsere Formation) → Ergebnis → zurück zur Auswahl
   mit "Challenge!" (1080,1010), Refresh 6/6 (830,1010), Back (704,1010).
4. Arena-I-Prep (Heldengrid + Battle (960,1010)) erscheint im Kette-Modus.
Achtung: Zahlen oben links/rechts (50,090 / 10,971) wechseln pro Screen —
vermutlich berechnete Team-Power, NICHT Gold (Gold nur im Menü-Kopf "4856K").
Rest: Skript `afk_arena.py` (Schwächsten wählen → x Kämpfe → Defeat-Stop)
+ Daily-Integration ("Challenge in Arena x6" 4/6).

### ✅ T36: Review-Fixes (Subagent-Batch, 17 Befunde) — eingezogen 223ccde, Live-Verifikation grün
Priority-3-Paket vor der nächsten Scheduler-Änderung (Subagent-Review deleg_d9aeeddd):
1. [HIGH] watch.sh: Lock stale nach 180 s < Worst-Case-Runtime → Schwellwert ~20 min +
   PID-Präfix für Screenshot-Namen (Kollisionen bei parallelen Läufen).
2. [MED] afk_claim_vision classify(): POPUP-Prüfung vor WORLD reihen (Overlaps),
   Chip-Fallback an lb>140 gate (Popup-klassifiziert als PANEL = Kauftap-Risiko).
3. [MED] UNKNOWN-States: blindes Recovery-Tapping in afk_claim_vision/afk_dailies/
   afk_stage_push (DEFEAT-By-Through, (960,910)-Tap) → abort(exit 1) statt Tap.
4. [MED] afk_dailies: Guild-Tab wird nie geöffnet (Rewards nie geclaimt) — Tab-Tap +
   Verifikations-Probe einbauen.
5. [MED] afk-bot-watch.sh: bare `python -c 'import PIL'`-Fallback droht im Scheduler
   → Interpreter-Pfad fixieren oder laut failen (kein blind-gated CLI-Fallback).
6. [LOW-Batch]: struct.unpack-Guard (leere power.bin), img.close(), Idle-Re-Check
   zwischen Phasen, exit-code-Doku (4/5), dedizierte Probes statt Doppelbelegung
   (200,270)/(960,300), adb-Rückgabecodes prüfen, LAUNCHER-Früh-Ausstieg.
- 🟦 T27-Update (19:2x): `afk_arena.py` Fight 1 verifiziert (changed=True), aber
  Fight 2 hängt: nach dem Fight resultiert eine **Victory-Karte**, die einen Tap
  zum Schließen braucht, bevor „Challenge!“ → Select → Prep → Battle greift.
  Sig-Vergleich bestätigt: Screen nach Fight 2-Tap = unverändert grau (Select).
  Fix offen: zwischen „Challenge!“ und Opponent-Tap ein Card-Dismiss (Tap 480,300
  oder Back) einbauen + Sig-Verifikation. Danach Daily-Integration (x6-Zähler).
- 🟦 T27a (Sergej-Klarstellung 19:08): Die Zahl in der roten Box je Gegnerkarte
  ist die **Kampfkraft** (10K / 39K / 75K) — nicht die Rangpunkte (1150/1250/1365).
  Schwächster Gegner = kleinste Kampfkraft. Zu prüfen: ist die Liste aufsteigend
  sortiert (dann ist "linke Karte" korrekt)? Wenn nicht: Ziffern-Reader für den
  Power-Strip (Template-Matching) oder Refresh-bis-schwächster-links.
- ✅ T27b (YAGNI-Schnitt 19:3x): Mehrkampf-Kette ist fragil (Victory-Card-Dismiss +
  Prep-Erkennung). Statt State-Loop-Feintuning: `afk_arena.py --fights 1` ist der
  verifizierte Pfad (3 Live-Läufe, changed=True), der Scheduler ruft es N-mal auf.
  Multi-Fight-Chaining bleibt als optionaler Ausbau notiert, nicht als Blocker.

- 🟦 T28-Update (Dream Realm live verifiziert): Hub -> Battle (960,1040) ->
  Elite-Challenge-Prep -> Battle (960,1010) -> ~70 s Bossfight -> **Victory
  Rewards** (2 Briefe) und danach eine **Vollbild-Hero-Card** (Dazzling DPS /
  Untouchable), die einen Tap außen (z. B. 100,100) zum Schließen braucht.
  `scripts/afk_dream_realm.py` gebaut; offene Fix-Baustelle: Hero-Card-State
  (hell Vollbild, L(960,300) > 190) als eigener Zustand + Dismiss. Versuche:
  Chances 7/7, jedes Fight-Ergebnis verbraucht einen Versuch.

### 🟦 T29-Update: Legend Trial + Arcane Labyrinth explor — key-gated
Beide Modi öffnen dieselbe Turm-Struktur (Light/Nature/Eternity/Will bzw. die
Labyrinth-Variante), Floor 1/80 mit „Challenge!“ (z. B. 1080,730) und einem
**Key-Vorrat ×3** oben links („5 more floors required“). Jeder Floor kostet
einen Key. Light/Will sind „Not Available“ (Wochentag-abhängig).
→ Automatisierung wäre trivial (Go → Challenge → Battle, gleiche Gates), aber
**verbraucht die begrenzten Keys** — deshalb wie T33 blockiert auf Sergejs
Ressourcen-Regel (Vorschlag: Keys nur verbrauchen, wenn Sergej es sagt, da sie
ggf. für andere Türme/Progression vorgehalten werden sollen).

### 🟦 T30-Update (22:3x): Homestead-Ernte — Mechanik noch ungeklärt
Feld-Taps (1420,710) senden den Helden NICHT zum Feld (er bleibt auf dem
Respawn-Kreis). Die Beträge je Feld wachsen kontinuierlich (3078→3140 in
Minuten) = anrechenbare Ernte. Offen: Abholung über Interact-Menü am Feld oder
zentralen Collect-Button? Nächster Schritt: Held von Hand an ein Feld schicken,
Interact-Menü analysieren (Harvest-Button?), dann Skript mit walk-waits.
Kamera-Abhängigkeit der Feld-Positionen: Icon-Probe statt fixer Koordinaten.
### ✅ T32 (YAGNI-Grad dokumentiert): SKILL.md-Hygiene
AFK-spezifische Sektionen in references/afk-journey-live.md ausgelagert
(25.5k -> 21.9k chars). Rest = Skill-Kern (ADB-Workflow + universelle Pitfalls),
bewusst behalten: das ist die maschinenverifizierte Kernkompetenz. Weitere
Kuerzung wuerde das Herz fragmentieren - Advisory-Warning akzeptiert.
### ✅ T37: Selbstfahrer — Cron-Job treibt die Queue endlos (2026-11-01 00:24)
Hermes-Cron **"Spectre Queue Driver"** (job 0a43fdced857, alle 30 min, forever,
continuity=on, workdir=Repo): jeder Lauf nimmt den nächsten offenen P5-Punkt,
verifiziert live, committet, markiert. Safety im Prompt: keine Käufe/Keys/
Leveling (T29/T33/T35 bleiben Policy-Blocker), Lock-Check gegen den 15-Min-Task
(.spectre/afk-bot.lock < 20 min = warten), Patch-Dateien statt heredoc-Quoting.
Queue-Laufs landen im Cron-Historie + TODOS.md. Stop: cronjob_manage pause/remove.
- 🟦 T30-Fund 2 (00:1x): Die Homestead-Kamera driftet (Scheduled-Läufe + Taps
  schieben sie). Welt-Anker (Battle Modes-Button, Login Rewards) sind
  kamera-abhängig — Feld-Taps landen dann auf falschen Objekten (Battle Modes
  statt Feld). Kandidat für Kamera-Reset: der Kompass-Button (960,800) (unklar).
  Nächster Versuch: Compass-Tap → verifizieren, dass die Feld-Icons an den
  bekannten Positionen wieder auftauchen → dann Walk+Harvest-Flow.
- 🟦 T30-Fund 3 (00:2x): Der Compass-Tap (960,800) rezentriert die Kamera Richtung
  Homestead-Mitte (verifiziert: Turm + Held + Feld-Icons sichtbar, Beträge
  1711/3422 wachsend). Meldung „Treiven and others received your help." = passive
  Homestead-Hilfe läuft. Offen bleibt: der eigentliche Abhol-Mechanismus (die
  Feld-Icons zeigen Beträge, aber kein Harvest-Button bisher sichtbar). Das
  T30-Rest bleibt Exploration; Compass = Kamera-Reset-Verfahren dokumentiert.
### ✅ T31: Mail/Quest-Reminder — bereits implementiert (verifiziert)
Der Marker `.spectre/dailies-last.txt` in watch.sh macht die Routine 1×/Tag —
live verifiziert (Routine lief, Marker gesetzt). Kein Rest.

### ✅ T30 (geschlossen, YAGNI): Homestead-Ernte = nichts zu automatisieren
3 Versuche: Feld-Taps senden den Helden nicht, kein Harvest-Button gefunden,
Beträge wachsen passiv, „...received your help." feuert selbstständig. Lesart:
das Spiel sammelt automatisch (Worker-System), die Feld-Icons sind nur Anzeige.
Falls Sergej einen manuellen Harvest-Weg kennt: Queue wieder öffnen, sonst
closed — nichts zu automatisieren.

### 🟨 Feature-Notiz (00:4x): Noble Tavern Recruit — Flow ungeklärt, Shop-Gefahr
Der Tap auf das Tavern-Gebäude öffnete den **Recruitment Store** (Shop mit
Kauf-Items, Preise, Qty-Angaben) — NICHT den Recruit-Screen. Sofort verlassen.
Der eigentliche Recruit-Flow (Einzel-Recruit mit 1 Ticket, Daily-Quest
„Recruit in Noble Tavern x1") braucht eine eigene Vermessung — Blind-Taps in
Shops sind tabu (Kauf-Risiko). Tickets: 1.260 vorhanden, nicht dringend.
### 🟨 T38-Update: Noble Tavern Recruit — kostet 300 DIAMANTEN, nicht Tickets
Recruit 1 (780,874) öffnete „Use Diamond x300?“ (Cancel/Confirm) — die 1.260
Invite-Letters wurden NICHT automatisch verwendet. Darüber ein „Rate Up Limited
Bundle I“ für 98 (echtes Geld!). Cancel getippt, nichts gekauft. Der Recruit
über Tickets braucht vermutlich einen Währungs-Toggle am Recruit-Button —
Vermessung nötig. Bis dahin: Recruit-Feature blockiert (300💎 = Policy).

### 🟦 T38-Update 2 (01:1x, Queue-Driver): Dream Realm hat MEHRERE Boss-Tiers
mit getrennten Chance-Pools. Die Boss-Page zeigte (nach den 7 Elite-Chancen
verbraucht): **Snow Stomper (Common I), Chances 7/7** NEBEN dem morgigen
Necrodrakon (Common II, dort 4/7). D.h. pro Tier existiert ein eigener
Daily-Pool — potenziell 7 WEITERE tägliche Kämpfe. Offen: (a) Flow zu den
anderen Tiers navigieren (Tier-Auswahl auf der Boss-Page? Pfeile/Tabs?),
(b) prüfen, ob `afk_dream_realm.py` tier-agnostisch funktioniert (Probes
sind auf die aktuelle Boss-Page kalibriert), (c) Kämpfe sind denselben
Policy-Regeln unterworfen (keine Käufe im Flow). Nächster Schritt: Boss-Page
live vermessen (Screenshot + Probe der Tier-Nav-Elemente) — erst dann
Queue-Eintrag als Task.

### 🟨 Scheduler-Log-Review (2026-11-03)
- P5-Queue ist leer. Vor dem Fix endeten die AFK-Scheduler-Logs am 2026-11-01; der letzte Daily-Run meldet einen veralteten `team_power`-Offset und fällt auf die Screen-State-Gates zurück, der Stage-Push endete regulär bei `DEFEAT`. Der sichere No-Device-Test hat danach `.spectre/logs/afk-bot-2026-11-02.log` mit Startmarker + `game process not found` (Exit 2) angelegt; keine Game-Taps.
- Windows-Aufgaben `Spectre AFK Daily` und `Spectre AFK Progress` sind aktiviert, melden aber als letzten Lauf 2026-11-02 18:36 mit Ergebnis `0x800710E0`; danach gibt es keinen Scheduler-Logeintrag. `net helpmsg 4320` übersetzt den Code als „Anforderung vom Operator oder Administrator zurückgewiesen“. Beide Task-XMLs setzen `DisallowStartIfOnBatteries=true` und `StopIfGoingOnBatteries=true` — möglicher, aber nicht bestätigter Auslöser; Task-Scheduler-History ist deaktiviert. Der sichere Aktivierungsversuch für `Microsoft-Windows-TaskScheduler/Operational` scheiterte mit „Zugriff verweigert“ (Exit 5). Batterie-Policy nicht geändert; Ursache bleibt ohne Admin-Rechte/History unbestätigt.
- Ursache für fehlende frühe AFK-Diagnosen: `afk-bot-watch.sh` erstellte das Tageslog erst nach Prozess-/Heap-Erkennung. Fix verifiziert: Startmarker und frühe Lock-/Prozess-/Heap-/Python-Fehler werden jetzt sofort ins Tageslog geschrieben; der No-Device-Test belegt Startmarker, Fehlergrund, Exit 2 und Lock-Cleanup.
- Queue-Driver-Review 00:59 CET: Das Tageslog 2026-11-02 enthält inzwischen zwei zusätzliche `mode=manual`-Starts (2026-11-02T23:23:14Z und 23:25:07Z); beide enden früh mit `game process not found`. Das bestätigt, dass die frühe Diagnose protokolliert wird, ist aber kein Scheduler-Lauf. `Spectre AFK Daily/Progress` stehen weiter auf letzter Lauf 02.11. 18:36, Ergebnis `0x800710E0`; nächste Läufe 03.11. 05:10/17:10. Batterie-Policy unverändert gelassen. Keine Codeänderung aus diesem Logbefund gerechtfertigt; P5 bleibt leer.
- Queue-Driver-Review 01:16 CET: Keine neuen Scheduler-Logblöcke seit 00:59; die erneute Task-Abfrage bestätigt beide Aufgaben als `Ready` und zeigt zusätzlich `StartWhenAvailable=false` (neben den bestehenden Batterie-Gates). Der TaskScheduler-Operational-Kanal bleibt deaktiviert; `HD-Player.exe` läuft nicht und der AFK-Lock fehlt. Ursache für `0x800710E0` bleibt unbelegt; keine Task-/Batterie-Policy geändert. In P5 ist kein unbearbeiteter `⬜`-Punkt offen; keine Game-Taps.
- Queue-Driver-Review 04:09 CET: `.spectre/logs/` fehlt und der AFK-Lock ebenfalls. `Spectre AFK Night` steht auf `Ready`, letzter Lauf 03.11. 02:00 mit `0x00000000`; das liegt vor Commit `0cc629d` (04:06) und beweist den R12-Fix nicht. Daily/Progress bleiben `Ready`, letzter Lauf 02.11. 18:36 mit `0x800710E0`, nächste Läufe 05:10/17:10; `StartWhenAvailable=false` und Batterie-Gates bleiben aktiv. TaskScheduler/Operational ist deaktiviert, daher ist der Night-Run ohne Tageslog nicht verifizierbar. Keine Policy geändert, keine Game-Taps. R12 steht auf `origin/main`; Fresh-Eyes fand einen hardcodierten Windows-Temp-Pfad im Regressionstest, der durch `TemporaryDirectory()` ersetzt wurde. Finaler Review ohne Befund; Testlauf 1/1 und Gesamtsuite 189 Tests grün (22 skipped; 139 Screenshot-Manifestframes lokal fehlend/skipped).
- Queue-Driver-Review 04:34 CET: P5 weiterhin ohne offene `⬜`-Punkte. `.spectre/logs/` enthält nur `bluestacks-ensure.log` mit dem heutigen eigenen Read-only-Check `04:34:10 ... check: ok`; kein AFK-Tageslog und kein Lock. `Spectre AFK Night`: `Ready`, letzter Lauf 03.11. 02:00, Ergebnis `0x00000000`, nächster Lauf 04.11. 02:00 — weiterhin kein Post-R12-Livebeleg. `Spectre AFK Daily/Progress`: beide `Ready`, letzter Lauf 02.11. 18:36, Ergebnis `-2147020576` (`0x800710E0`), nächste Läufe 03.11. 05:10/17:10. Keine neuen Logdaten erklären die Ablehnung; Batterie-Policy und TaskScheduler/Operational unverändert gelassen. Keine weitere Scheduler-Codeänderung aus diesem Befund gerechtfertigt.
- Queue-Driver-Review 12:45 CET 2026-11-03: keine neuen Logblöcke seit dem
  05:10-Daily; 17:10-Progress (erster Post-Fix-Livebeleg) steht aus. Die wieder-
  kehrenden „team_power guard disabled“-Zeilen im Daily-Log sind erklärt: die
  Anker-Datei `power-state.json` fiel dem .spectre-Teardown zum Opfer — Anker
  wiederhergestellt, Guard wieder online (siehe T44-Nachtrag). Kein Code-Change.

- Queue-Driver-Review ca. 06:12 CET: Der Daily-Log vom 03.11. 05:10 (`.spectre/logs/afk-bot-2026-11-03.log`) bestätigt Chest-Claim, Gift-Warnung und Fehler in Arena (`STUCK`), Dream Realm (World nicht erreicht) und Stage-Push (unerwarteter BATTLE-State). Task Scheduler meldet dennoch Last Result `0`; der Lauf startete um 05:10 und liegt vor Commit `da9f411` (05:47 CET), daher ist das kein Gegenbeweis zum Phase-Exit-Fix und kein Post-Fix-Livebeleg. Keine weitere Scheduler-Änderung gerechtfertigt; Daily-Verifikation steht beim nächsten Daily-Lauf 04.11. 05:10 aus.
- Queue-Driver-Review 07:29 CET: P5 hat keinen offenen `⬜`-Punkt; seit dem 05:10-Daily-Log kam kein weiterer AFK-Logblock hinzu. Task Scheduler bestätigt Daily `03.11. 05:10`, Last Result `0`, obwohl das Log Arena=`STUCK`, Dream Realm=World nicht erreicht und Stage-Push=unerwarteter `BATTLE` meldet; dieser Lauf liegt vor `da9f411` (05:47 CET). Progress bleibt `Ready`, letzter Lauf `02.11. 18:36`, Result `0x800710E0`, nächster Lauf heute 17:10. Night meldet `03.11. 02:00`, Result `0`, aber das war vor `00cc629d` (04:06 CET); kein eigener AFK-Night-Log vorhanden. Regressionstest des Daily-Exit-Fixes ist durch die Gesamtsuite bestätigt: 191 Tests ausgeführt, davon 22 übersprungen (169 bestanden); Frame-Regression übersprang alle 139 Einträge wegen fehlender lokaler Screenshots. Kein weiterer Code-/Task-Policy-Eingriff gerechtfertigt; Batterie-Gates unverändert, keine Game-Taps. Post-Fix-Livebelege stehen bei Night 04.11. 02:00 und Daily 04.11. 05:10 aus.
- Queue-Driver-Review 23:09 CET 2026-11-03: P5 enthält keine aufgabenbezogene
  `⬜`-Checkbox; Scheduler-Logs geprüft. `.spectre/logs/afk-bot-2026-11-03.log`
  endet beim 17:10-Progress-Lauf (mtime 17:11). Der 05:10-Daily-Run protokolliert
  Arena=`STUCK`, Dream Realm erreicht WORLD nicht und Stage-Push bricht auf
  `BATTLE` ab; dieser Lauf liegt vor den späteren Recovery-Fixes und ist kein
  Post-Fix-Beleg. Progress: Chest-Claim verifiziert, x2-Autobattle, zwei Kämpfe
  übersprungen, Wand erreicht bei Stage 254 / Power 74986; Scheduler Result 0.
  Der dortige Guard-Read 108449240 ist der Vor-Fix-Befund, nicht der aktuelle
  Live-Wert. Daily/Progress/Night sind `Ready`, Last Result jeweils 0; nächste
  Läufe 04.11. 05:10 / 17:10 bzw. 02:00. Keine Logs nach 17:10, kein AFK-Lock.
  Kleinste sichere Verbesserung umgesetzt: Revalidator verwirft gleichrangige
  u64-Ties und Map-Aliase auch mit nicht-null Hash bzw. High-Bit-u32 fail-closed;
  Regressionen decken rohe Fixture-Bytes ab (inkl. korrekt innerhalb 1024 B
  liegender Tie-Kandidaten). MCP-Livebeleg: BlueStacks/ADB `device`, Spiel-PID
  5176, rw-Heap `0x796590000000`; `u64 @ 0x796590A67A54` = 259160. Nach MCP-Exit
  lieferte `memory_preflight` `('ok', 259160)`; State blieb PID/Base/Offset/Width
  konsistent. Keine Game-Taps. 23 Guard-Tests grün; Gesamtsuite 272 Tests OK,
  22 übersprungen; Frame-Regression `checked=62 skipped=0`. Finaler Fresh-Eyes-
  Review ohne sicherheitskritischen Befund; keine Task-/Policy-Änderung nötig.

- Queue-Driver-Review 01:06 CET 2026-11-04: P5 hat weiterhin keine offene
  aufgabenbezogene `⬜`-Checkbox. `.spectre/logs/afk-bot-2026-11-03.log` blieb
  unverändert (mtime 17:11); Night/Daily/Progress sind `Ready`, Last Result 0
  vom 03.11., nächste Läufe heute 02:00/05:10/17:10. Kein Scheduler-Lauf
  erzwungen, keine Game-Taps.
  Live-Nachprüfung des `91151af`-Guards (Heap-Churn hat den 23:09-Read-back
  `0xA67A54` = 259160 inzwischen überholt): der gespeicherte u64-Anker
  `0xA67A54` las als 55,834,836,546 (Bytes: u32 261698 + Hash 13, kein
  gültiger Heap-Pointer) und wurde fail-closed neu lokalisiert. `memory_preflight`
  lieferte `('ok', 258488)` und aktualisierte den State auf Offset
  10,943,092 (`0xA6FA74`); MCP-Read-back bestätigte PID 5176, Heap-Basis
  `0x796590000000` und exakt 258488 am neuen Slot `0x796590A6FA74`.
  Keine weitere Code-/Task-Policy-Änderung aus den unveränderten Scheduler-Logs
  gerechtfertigt; nächster Post-Fix-Night-Beleg steht nach dem 02:00-Lauf aus.

## P6 — Idle-Architektur (Sergejs Korrektur, 2026-11-01)
> 15-Minuten-Chest-Claims bringen bei einem Idle-Game NICHTS (fixe Rate, 12-h-Cap).
> Der Hebel ist Progression: hohe Stage = hohe Rate, Heldenpower = hohe Stage.

- ✅ T39: Scheduler umgebaut: Task "Spectre AFK Daily" 05:10 (nach Reset) macht
  alles (Chest, Quests 5 Tabs, Mail, Login, Arena 4/4, Dream Realm 7/7,
  Stage-Push bis Wand); Task "Spectre AFK Progress" 17:10 macht Chest (Cap-Schutz)
  + Stage-Push. 15-Minuten-Task gelöscht. Idle-Gate bleibt.
- ✅ T40: Stage-Push in den Progress-Run — erledigt 2026-11-01. `afk_stage_push.py`
  läuft im Daily- (T39, 05:10) und Progress-Run (17:10) mit `--auto --auto-minutes 6`,
  E2E inkl. Welt-Einstieg (AFK-Progress-Chip), Klassifikator-Reorder, Live: Stage
  218→254. Commits 041c762, b1f991a, 46c082c; Night-Mode `--retry-defeats` (cc68503,
  paralleler Writer).
- ⏸️ T33: Helden-Leveling — jetzt DER zentrale Hebel (Rate × Level), braucht Regel.
- ✅ T41: Wand-Report — erledigt 2026-11-01 (Commit 46c082c). `wall_report()`
  schreibt JSONL nach `.spectre/wall-report.log` (Stage/Power via Offline-WinRT-OCR,
  `templates/ocr.ps1`) an allen Wand/Exit-Punkten. Live bewiesen: stage=254
  power=74986; States Auto-Battle-Complete/CONFIRM/POPUP behandelt.
### 🟨 T42-Update: AFK Synergy Battle (1/1) — nutzt den Proxy, löst die Wand NICHT
Der Defeat-Screen bietet „AFK Synergy Battle (1/1)" (Position 930,866) — der
Proxy-Modus (starke Fremd-Formation). Live getestet: Kampf lief 76 s, endete
mit „Turn off Auto Battle mode?"-Dialog, **AFK Progress blieb 249**. Die Synergy
Battle ist vermutlich kein Stage-Kampf, sondern ein eigenes Event — Verbrauch
1/1, Fortschritt null. Daily-Quest „Assist in Proxy/Synergy x2" bekommt dadurch
aber Progress (1/2). Cancelt (X 1014,710).
Noch offen für die Wand: Helden-Leveling über Resonanz-Panel — Exploration
scheiterte bisher an Auto-Battle-Interleaving (navigiert mit Verifikation bei
jedem Schritt nötig, nicht blind).
### 🟢 T42-Meilenstein (02:24): Stage 249 → 252 — die „Wand" wandert
Messung über ~2 h Auto-Battle-Retries: 249 → 250 → 251 → 252. Der „Defeat" ist
kein harter Stopp — das Auto-Battle retried denselben Stage und gewinnt
irgendwann (Resonanz-/Power-Drift durch passive Income?). Die Stage-Push-Logs
(T34, 1×/Tag) sind damit effektiver als angenommen: --auto bis zur DEFEAT-Karte,
dann retryt das Spiel weiter.
Feature-Idee daraus: Push-Loop nachts über mehrere Stunden (idle) = freier
Stage-Fortschritt ohne Eingriff. Hero-Level-Boost beschleunigt zusätzlich.
Dialog-Gotcha: „Turn off Auto Battle mode?" erscheint nach jedem
Battle-Ende/Synergy-Ende — Cancel-Tap (1014,710) nötig, sonst blockiert der
Dialog die Navigation. Einmaliges Bestätigen schaltet Auto Battle aus
(reversibel) und befreit die Navigation — aber stoppt den Progress-Loop.

### ✅ T43: Review-Fix-Batch MED/LOW für `afk_stage_push.py` — erledigt 2026-11-01
(Commit a3ed421; Nummer T43 statt T42, weil T42 von den Synergy-Battle-Notizen
belegt ist.) Frisch-Augen-Review der aktuellen Datei ergab 19 Befunde; 16
eingezogen, 2 bewusst nicht (siehe unten), 1 teilweise:
1. [MED] RESULT-Branch in der Auto-Chain-Loop: Victory-Karte mid-chain wird
   geschlossen und Auto Battle neu bewaffnet (inkl. x2-Re-Tap — LOW #13 mit).
   Vorher spinn die Loop stumm bis zum Timeout; im Night-Mode wäre jeder
   Retry-Sieg verloren gegangen.
2. [MED] DEFEAT in den Single-Wait-Sets + expliziter DEFEAT-Stop mit
   wall_report; PREP nach Battle-Tap = ein Re-Tap statt Fehl-Abbruch (LOW #18).
3. [MED] LAUNCHER mid-chain → wall_report + Exit 3.
4. [MED] Idle-Recheck pro Loop-Iteration (Chain + Single) → Exit 5, keine
   Taps mehr, sobald der PC in Benutzung ist.
5. [MED] Retry-Verifikation + Cap: nach Retry-Tap wait_for(BATTLE/PREP/
   LOADING/CONFIRM), CONFIRM wird gecancelt; Cap 200 Retries; wall_report im
   Night-Mode gedrosselt (1. + jeder 10. Defeat).
6. [MED] CONFIRM/POPUP-Gates VOR dem bright-card-Branch in classify_battle
   (Popup zählte vorher als Victory/RESULT → Blind-Tap (960,540) aufs
   Store-Risiko). WICHTIG: nach dem BATTLE-Check belassen — Nachtkampf-Frames
   lesen als v.classify POPUP (shots-36248 sp_auto_3/_14) und müssen BATTLE
   bleiben. Regression über 231 archivierte Frames: nur 2 Diffs, beide sind
   genau die beabsichtigte Verbesserung (falsch-RESULT → POPUP).
7. [MED] wait_for/Chain-Loop tolerieren transiente adb-Fehler (Retry statt
   Traceback-Abbruch); Top-Level-Handler → sauberer Exit.
8. [MED] Shot-Prune: nur die 30 neuesten PNGs bleiben (Disk-Leak über
   Nacht-Läufe); lazy TMP-mkdir; power.bin pro Run (Race gefixt).
9. [LOW] parse_stage geankert ('AFK Stage n' bevorzugt, looser Fallback nur
   Zeilenende) — Quest-Counter können nicht mehr als Stage lesen; Unit-Tests
   grün; Defeat-Screen liefert jetzt korrekt None statt Fehlwert.
10. [LOW] wall_report: png/ocr_ok/ocr_error-Felder in der JSONL, lines immer
    gesetzt, Write-Fehler landen im Record + in der Print-Zeile.
11. [LOW] OCR-Timeout 90→15 s; Exit-3-Doku; --battles wird nicht mehr still
    umgeschrieben (planned-Variable).
- Bewusst NICHT gefixt: SKIP-Button-Farbprobe (Review #10) — Messung an
  echten Battle-Frames zeigt, dass (1220,788) sehr variabel ist und echte
  Nachtkampf-Frames teilweise als POPUP klassifizieren; ein Gate dort würde
  funktionierendes Skip-Verhalten brechen. BATTLE-Klassifikation (Pause-
  Probe) bleibt der Schutz.
- Live-Verifikation (3 Läufe): Auto-Chain → DEFEAT → wall_report → Exit 0;
  Night-Mode-Retry live (Retry → verifiziert → PREP-Debounce → wall_report
  mit stage=254 power=74986); Prune aktiv (10 PNGs nach 2-Min-Run).

### ✅ T44: team_power-Offset-Revalidation nach Game-Restart — erledigt 2026-11-01
Implementiert in `afk_claim_vision.memory_preflight` (alle 5 Skripte erben es):
- Bei 'stale' werden die ersten 16 MB des Hot-Heaps ZWEIMAL (5 s Abstand) gedumpt
  und in EINEM Pass nach u32- UND u64-Slots im Anker-Fenster gescannt
  (`scan_slots`, Prefilter: high bytes == 0 → ~4 M Slots in Sekunden).
- **Schlüsselfund (Live-Messung):** Nach dem Restart ist Team-Power KEIN u64-Feld
  mehr, sondern ein **u32 Map-Entry**: `[u32 value][u32 hash][ptr → Heap]` —
  259850 liegt stabil bei `base+0x2FE8`, 8-aligned, mit Heap-Pointer +8. Der
  alte u64-Slot (+0xA578) ist weg (0 Treffer im u64-Muster).
- Filter: Alloc/Metadata-Shapes ausgeschlossen (v ≡ 0/1 mod 4096 — die Top-
  "Treffer" 2097152/1048576/… sind genau diese Muster), u64 braucht ≥2 Kopien
  (Display-Copies), u32 braucht 8-aligned + Pointer-Nachbar, Ranking nach
  Distanz zum Anker, Akzeptanz gedeckelt auf 10 % Drift.
- State: `.spectre/power-state.json` (offset/width/power/pid/base) — der letzte
  VERIFIZIERTE Wert ist der Anker für den nächsten Restart; 'ok'-Läufe
  aktualisieren ihn. Scheitert die Re-Location → Status **'disabled'** (Quiet-
  Line statt WARN-Spam; Vision-Gates tragen weiter die Sicherheit).
- **Live verifiziert:** Re-Location 11,7 s → ('ok', 259850) via offset 0x2FE8/
  width 4; Zweit-Preflight 0,1 s. Der Guard ist damit nach dem 2026-11-01-
  Restart WIEDER ONLINE.
- Einschränkung (dokumentiert): HUD-Gegenprobe (Resonating Hall „Power 2xxK“)
  wurde NICHT gezogen — PC in Benutzung (idle 0,05 s) + aktiver paralleler
  Writer zur Messzeit. Der gefundene Slot ist anker-verifiziert (exakter Wert =
  letzter verifizierter Memory-Wert, stabile Map-Entry-Struktur); ein falscher
  Kandidat mit exakt diesem Wert + Pointer-Struktur ist unwahrscheinlich.
- ✅ **T44-Nachtrag (2026-11-03 12:47 CET, Queue-Driver): Anker-Datei nach dem
  .spectre-Teardown wiederhergestellt — Guard für PID 5176 wieder ONLINE.**
  Root Cause: `power-state.json` fiel dem Junction-Teardown (R13) zum Opfer;
  ohne `power`-Anker geht `memory_preflight` direkt auf 'disabled' (Re-Location
  überspringt sich selbst) → jeder 05:10-Lauf loggte „guard disabled“. Fix
  (read-only, kein Game-Code-Change): Idle 223 s + Lock-frei verifiziert →
  Screenshot/OCR (Homestead ohne Power-HUD) → Resonating-Hall-Tap (1000,1030)
  liest **Power 259K** (konsistent mit dem letzten verifizierten exakten Wert
  259850) → Panel per Back geschlossen, WORLD verifiziert → State-File mit
  Anker 259850 geschrieben → `memory_preflight('5176','0x7964E0000000')`:
  **Re-Location ('ok', 259850) in 11,7 s** (u32 Map-Entry, offset 1824824 =
  0x1BD838 [korrigiert 13:05 — der hier zuerst notierte Hexwert 0x1BD518 war
  ein Rechenfehler; die State-File war korrekt], width 4, base
  0x7964E0000000) → Zweitread 10 s später unverändert 259850,
  Preflight-2 in 0,13 s ('ok'-Pfad). Der 17:10-Progress-Run hat den Guard damit
  wieder scharf; bei einem weiteren Game-Restart re-lokaliert die Maschine jetzt
  wieder aus einem frischen Anker. Belege: .spectre/shots-5176/anchor-*.png,
  .spectre/power-state.json.
  **Re-Check 13:05 CET (Queue-Driver, rein read-only):** PID 5176 lebt weiterhin,
  `spectre dump` am absoluten Offset (base + 0x1BD838) liest unverändert
  `0a f7 03 00` = **259850** — Anker gültig, der 17:10-Lauf geht direkt über
  den 'ok'-Pfad (0 Re-Location, 0 Taps). Keine neuen Logblöcke seit dem
  **Re-Check 13:21 CET (Queue-Driver, rein read-only):** PID 5176 + rw-Heap
  `7964e0000000-7964e7e00000` weiter in maps, Direkt-Read am Anker
  (skip=133474163611704) liest unverändert `0a f7 03 00` = **259850** —
  Anker gültig, 17:10-Progress geht weiter über den 'ok'-Pfad. Keine neuen
  Scheduler-Logblöcke seit dem 05:10-Daily (Log-Stand 05:23).
  **Re-Check 14:10 CET (Queue-Driver, rein read-only):** identisches Bild —
  Device reachable, `pidof` bestätigt Spiel-PID 5176, Direkt-Read am Anker
  (skip=133474163611704) liest unverändert `0a f7 03 00` = **259850** — Anker
  gültig, 17:10-Progress geht weiter über den 'ok'-Pfad. Kein Lock, keine neuen
  Logblöcke (Log-Stand 05:23). Task-Scheduler: Progress `Ready`, nächster Lauf
  heute 17:10 (Last Result weiterhin 0x800710E0 vom 02.11.); Daily → 04.11.
  05:10 (Result 0), Night → 04.11. 02:00. Repo-Suche nach `tasklist //FI`
  bestätigt: KEIN Repo-Skript nutzt den Filter (alle greppen die volle
  tasklist-Ausgabe) — das 13:53-Quirk betraf nur Ad-hoc-Diagnosen, die
  TODOS-Notiz deckt es ab; kein Code-Change nötig.
  **Re-Check 13:53 CET (Queue-Driver, rein read-only):** identisches Bild —
  Device reachable, Spiel-PID 5176 via `pidof` bestätigt, Direkt-Read am
  Anker (skip=133474163611704) liest unverändert `0a f7 03 00` = **259850**;
  HD-Player.exe läuft (Windows-PID 82600, im Bot-Kontext irrelevant — Anker
  ist pro Android-Prozess gültig). Kein Lock, keine neuen Logblöcke
  (Stand 13:04). Hinweis für künftige Läufe: `tasklist //FI` (MSYS
  double-slash) verfälscht den Filter → meldet fälschlich „NOT running";
  `/FI` (im Bash-Kontext als `/FI` oder `'/FI'` quoted) nutzen oder den
  Android-seitigen `pidof` als Prozessnachweis nehmen. Keine Taps, kein
  Code-Change; nächster Meilenstein bleibt der 17:10-Progress-Lauf mit
  R15/A8-Live-Checks + Frame-Manifest-Regen (R13).
  **Re-Check 14:26 CET (Queue-Driver, rein read-only):** identisches Bild —
  Device reachable, `pidof` bestätigt Spiel-PID 5176, Direkt-Read am Anker
  liest unverändert `0a f7 03 00` = **259850** — Anker gültig, 17:10-Progress
  geht weiter über den 'ok'-Pfad. Kein Lock, kein neuer Logblock (Stand 05:23).
  Task-Scheduler unverändert (Progress Ready → 17:10; Daily/Night Result 0 →
  04.11.). **Parallel-Writer-Beobachtung:** neuer lokaler Worktree
  `C:/Users/Sigi/spectre-tray` auf Branch `feature/T66-tray-icon` (Commit
  c9ef793, nicht gepusht; T66 fehlt noch im Wave-3-Plan) — Tray-Icon-Feature
  in Arbeit, hier NICHT angefasst. `.spectre` auf 244 MB geschrumpft
  (Trash-Auto-Age wirkt; R10-Befund 1,3 GB erledigt).
  **Re-Check 14:43 CET (Queue-Driver, rein read-only):** identisches Bild —
  Device reachable, `pidof` bestätigt Spiel-PID 5176, Direkt-Read am Anker
  liest unverändert `0a f7 03 00` = **259850** — Anker gültig, 17:10-Progress
  geht weiter über den 'ok'-Pfad. Kein Lock, kein neuer Logblock (Stand 05:23),
  `git pull --ff-only` up to date (`7a78078`). Task-Scheduler unverändert
  (Progress Ready, Last 02.11. 18:36, Result 0x800710E0, Next heute 17:10;
  Daily/Night Result 0 → 04.11.). **Tool-Notiz:** `schtasks //Query //TN …`
  wurde diesmal von schtasks als „Ungültige Option //Query" abgelehnt (MSYS
  doppel-slash landete als Literal) — zuverlässige Routine ist
  `powershell -NoProfile -Command 'Get-ScheduledTaskInfo -TaskName …'`
  (Single-Quotes gegen bash-$-Expansion). Keine Taps, kein Code-Change.
- Scheduler-Nebennotiz erledigt: `--retry-defeats` an beide Stage-Push-Aufrufe
  in `afk-bot-watch.sh` (Progress-Run + Daily-Run) — afk-night.sh ist committed
  (cc68503), Kollisionsfenster vorbei.
- Achtung Parallel-Writer: cc86652 hat den T44-Zwischenstand blanket-add
  committet; der finale Algorithmus (u32-Support, Alloc-Filter, Distanz-Ranking,
  width im State) kam als Folge-Commit.
### 🟦 T33-Update (03:1x, OCR-verifiziert): Helden-Leveling — Kosten pro Batch ~47 % des Golds
Verifizierte OCR-Lese (WinRT, echte Textzeilen) vom Heldendetail (Shemira,
Hands of Resonance, Lvl. 74): „Level Up"-Button mit Kosten **2395K Gold +
63K EXP** und „2985/1100" — Wallet auf dem Detail-Screen: **5104K** (5,1 Mio).
D.h. ein Level-Up-x10-Batch kostet ~2,4 Mio Gold = **47 % des Bestands** —
über jeder vernünftigen Schwelle (10 % = 510K). Das x10-Button-Layout:
(1460,1065) und (1520,1005) starteten NICHT (Lvl. 74 blieb 74) — Button-
Position/Bedingung noch nicht verifiziert. Die Lvl-74-Werte zeigen auch:
**Resonance Heroes stehen auf 74, nicht auf Resonance-Level 80** (Widerspruch
zu Regel 2 im Rules-Panel — vermutlich liegt das Resonance-Level woanders).
→ T33 bleibt BLOCKIERT auf Sergejs Ressourcen-Regel, ABER jetzt mit echten
Kosten-Daten für die Entscheidung: ein Batch ≈ 2,4 Mio Gold (47 %). Gold
hat AFK-Journey-seitig nur diesen Zweck. Sergej entscheiden lassen: Batch
grün/rot pro Lauf, oder max X Batches/Woche. Tooling: OCR-Pipeline läuft
(templates/ocr.ps1), Wallet+Kosten lesbar — Umsetzung nach Freigabe ~1 Sprint.

## P7 — Mechanik-Gaps & Automation-Roadmap (Research 2026-11-01)
> Quelle: docs/research/mechanics-gaps.md (Wiki-confirmed [W] + community [C]).
> Queue-Discipline wie P5: sequenziell, Corrections werden angehängt.

- ✅ T45a: „Push past the cap still pays" — bereits abgedeckt (Stage-Push ohne Cap-Logik).
- ✅ T45b: Mystic Collection durch Daily-Chest — bereits abgedeckt (Quick Claim täglich).
- ✅ T45c: Instant AFK Attempts NACH dem Push claimen — ABGEDECKT (T45c-Update
  unten, 03:1x): das Chest-Popup hat nur EINEN Claim-Button (960,606), der die
  Daily „Claim Instant AFK Rewards x1" mit abhakt. Kein separates Feature.
- 🟨 T45d: Dura's Trials — Retry-bis-Sieg (Fail = Token-Refund, Tokens reset daily).
  Neuer Mode: Turm-Rotation (6 Tage, 2 Klassen/Tag) → class-gear Notes.
  🟨 Queue-Driver 03:4x: Umsetzung in DIESEM Lauf env-blockiert — BlueStacks-VM
  war aus (erst durch den Driver gebootet), aber der PC zeigt kontinuierliche
  Input-Bursts (idle nie > 60 s; Input alle 1–3 Min = aktive Nutzung). Idle-Gate
  (180 s) schlägt an → keine Game-Taps. Exploration (wo ist Dura's Trials im
  Menü, Token-Counter, Retry-Flow) im nächsten freien Fenster.
  🟨 Queue-Driver 20:32 CET: erneut env-blockiert. Idle-Probe = 0,016 s, VM/Spiel
  nicht gestartet (ADB 127.0.0.1:5555 ohne Device); daher keine Taps/Boot-Aktion.
  Dura-Menü, Token-Counter und Retry-Flow bleiben live unvermessen.
- 🟨 T45e: Arena auf 10 Tickets (5 frei + 5 gekauft = 10/Tag max); Defense-Formation
  setzen; über der Last-100-Champion-Linie bleiben (Wochenend-Demotion-Gamble).
  🟨 Queue-Driver 20:32 CET: live blockiert (Idle 0,016 s; kein ADB-Device).
  Die zusätzlichen 5 Versuche benötigen Käufe/Spielwährung; nichts gekauft oder
  angetippt. Defense-Formation und Champion-Linie deshalb ebenfalls unvermessen.
- 🟨 T45f: Legend Trial alle 4 Türme am SONNTAG (Rotation: Light Mo/Fri/Sun,
  Nature Wed/Sat/Sun, Eternity Thu/Sat/Sun, Will Tue/Fri/Sun) — Key-Release nötig (T29).
  🟨 Queue-Driver 20:32 CET: Policy-Blocker T29 — würde Legend-Trial-Keys
  verbrauchen; keine Freigabe, daher nicht angetippt.
- 🟨 T45g: Primal Lord (Event): Max-Damage-Run FIRST (Eternal Inscription zahlt
  alle späteren Claims zum Peak); ungenutzte Challenges werden claimbar (nicht verloren).
  🟨 Queue-Driver 20:32 CET: live blockiert (Idle 0,016 s; kein ADB-Device),
  Event-Status und Challenge-Verfügbarkeit nicht verifizierbar, keine Taps erfolgt.
- 🟨 T45h: Friend Favors (10/Tag → 1 Chest, Progress carry-over), Guild Activeness
  vor Sonntag, Homestead-Assists. Freie Chests + Build-Speed.
  🟨 Queue-Driver 20:32 CET: live blockiert (Idle 0,016 s; kein ADB-Device),
  Favor-Zähler/claimbare Chests und Guild/Homestead-States nicht verifizierbar.
- 🟨 T45i: Honor Duel: Rounds 1–2 unterbesetzen (Badges farmen), r8+ höchste Payouts.
  1 Duel-Ticket/Play (wie T29 — Policy).
  🟨 Queue-Driver 20:32 CET: Policy-Blocker T29 — jeder „Play Now“-Kampf kostet
  ein Duel-Ticket; keine Freigabe, daher nicht angetippt.
- 🟨 T45j: Season-End-Arbitrage (≤6h: Chest/Attempts NICHT claimen; Tag 1: Push → Claim;
  Season-Mats 24h vor Ende dumpen). Braucht Season-Kalender → sobald Season-Nähe
  erkennbar (Banner-Timer), Scheduler-Task.
  🟨 Queue-Driver 20:50 CET: live verifiziert blockiert — BlueStacks/HD-Player
  läuft nicht, ADB-Verbindung zu 127.0.0.1:5555 wird verweigert (10061), kein
  Device. PC-Idle 0 s; aus Sicherheitsgründen weder Emulator gestartet noch
  Spiel angetippt. Season-Banner/Timer damit nicht prüfbar; T45j bleibt offen.
  🟨 Queue-Driver 21:08 CET: erneut live blockiert — Lock fehlt, aber PC-Idle
  nur 0,016 s (<180-s-Gate); ADB 10061 / kein Device. Kein Emulatorstart und
  keine Game-Taps; Season-Banner/Timer weiterhin nicht prüfbar.
  🟨 Queue-Driver 21:25 CET: erneut live blockiert — PC-Idle 0 s (<180-s-Gate);
  ADB `get-state` meldet `device '127.0.0.1:5555' not found`. Kein Emulatorstart
  und keine Game-Taps; Season-Banner/Timer nicht prüfbar. T45j bleibt offen.
  🟨 Queue-Driver 21:46 CET: erneut live blockiert — PC-Idle 0,328 s (<180-s-Gate);
  ADB `get-state` meldet `device '127.0.0.1:5555' not found`; `.spectre/afk-bot.lock`
  fehlt. Kein Emulatorstart und keine Game-Taps; Season-Banner/Timer bleibt
  ungeprüft. T45j bleibt offen.
  🟨 Queue-Driver 22:04 CET: erneut live blockiert — PC-Idle 211,547 s (>180-s-Gate), Lock fehlt, aber BlueStacks/HD-Player läuft nicht; `adb connect 127.0.0.1:5555` verweigert die Verbindung (10061), kein Device. Gemäß Emulator-Prerequisite nicht gestartet; keine Game-Taps. Season-Banner/Timer ungeprüft; T45j bleibt offen.
  🟨 Queue-Driver 22:21 CET: erneut live blockiert — PC-Idle 117,641 s (<180-s-Gate), Lock fehlt; `adb connect 127.0.0.1:5555` verweigert die Verbindung (10061), `adb devices -l` meldet kein Device und `HD-Player.exe` läuft nicht. Kein Emulatorstart oder Game-Taps; Season-Banner/Timer bleibt ungeprüft, T45j bleibt offen.
  🟨 Queue-Driver 22:38 CET: erneut live blockiert — PC-Idle 638,172 s (>180-s-Gate), `.spectre/afk-bot.lock` fehlt, aber `HD-Player.exe` läuft nicht; `adb connect 127.0.0.1:5555` verweigert die Verbindung (10061), `adb devices -l` meldet kein Device. Gemäß Emulator-Prerequisite kein Emulatorstart und keine Game-Taps; Season-Banner/Timer ungeprüft. T45j bleibt offen.
  🟨 Queue-Driver 22:55 CET: erneut live blockiert — PC-Idle 1.665,062 s (>180-s-Gate), `.spectre/afk-bot.lock` fehlt; `HD-Player.exe` läuft nicht. `adb connect 127.0.0.1:5555` wird mit 10061 verweigert, `adb devices -l` ist leer und `get-state` meldet `device '127.0.0.1:5555' not found`. Daher kein Emulatorstart und keine Game-Taps; Season-Banner/Timer nicht prüfbar. T45j bleibt offen.
  🟨 Queue-Driver 23:12 CET: erneut live blockiert — PC-Idle 2.696,125 s (>180-s-Gate), `.spectre/afk-bot.lock` fehlt; `HD-Player.exe` läuft nicht. `adb connect 127.0.0.1:5555` verweigert mit 10061, `adb devices -l` ist leer. Gemäß Emulator-Prerequisite BlueStacks nicht gestartet; keine Game-Taps. Season-Banner/Timer weiter ungeprüft; T45j bleibt offen.
  🟨 Queue-Driver 23:29 CET: erneut live blockiert — PC-Idle 3,656 s (<180-s-Gate; gemessen via GetLastInputInfo), `.spectre/afk-bot.lock` fehlt, `HD-Player.exe` läuft nicht; `adb connect 127.0.0.1:5555` verweigert mit 10061 und `adb devices -l` ist leer. Kein Emulatorstart/keine Game-Taps; Season-Banner/Timer ungeprüft. T45j bleibt offen.
  🟨 Queue-Driver 00:02 CET 2026-11-03: erneut live blockiert — BlueStacks/HD-Player läuft nicht (`adb connect 127.0.0.1:5555` verweigert 10061, `adb devices` leer, `HD-Player.exe` nicht aktiv). Gemäß Emulator-Prerequisite kein Emulatorstart und keine Game-Taps; Season-Banner/Timer nicht prüfbar. T45j bleibt offen.
  🟨 Queue-Driver 02:08 CET 2026-11-03: `scripts/bluestacks-ensure.sh` erfolgreich (Exit 0: VM + ADB verbunden); Spielprozess PID 4392. Screenshot zeigt Battle Modes; Dream-Realm-Karte „Results in 22h“ ist kein belegter Season-End-Timer, und ein Season-Kalender/Banner ist auf diesem Screen nicht sichtbar. PC-Idle 9 s; keine Game-Taps, um die aktive Nutzung nicht zu stören. T45j bleibt offen: bei einem späteren idle-gated Lauf nach dem Season-Banner/Endtimer suchen. Manueller BlueStacks-Start ist nicht erforderlich.
  🟨 Queue-Driver 02:27 CET 2026-11-03: MCP-Health meldet BlueStacks + ADB erreichbar; `find igame` bestätigt PID 4392. Read-only-Screenshot `.spectre/shots-4392/readonly-season-check.png` zeigt erneut Battle Modes; „Results in 22h“ gehört zum Dream-Realm-Timer und belegt keinen Season-End-Timer. Kein Season-Banner/Kalender sichtbar. Lock fehlt, aber Windows-Idle nur 11 s (<180 s); keine Game-Taps. T45j bleibt offen.
  🟨 Queue-Driver 02:55 CET 2026-11-03: MCP-`health` meldet BlueStacks + ADB erreichbar, `find igame` bestätigt PID 4392. Neuer Read-only-Screenshot `.spectre/shots-4392/readonly-season-20261103-0255.png` zeigt Battle Modes, aber keinen Season-Banner/Kalender/Endtimer; „Results in 22h“ ist weiterhin nur der Dream-Realm-Timer. `.spectre/afk-bot.lock` fehlt; Windows-Idle 39,625 s (<180 s), daher keine Game-Taps. T45j bleibt offen.
  🟨 Queue-Driver 03:15 CET 2026-11-03: BlueStacks/ADB bereits erreichbar; `pidof` bestätigt Spiel-PID 4392. Read-only-Screenshot `.spectre/shots-4392/readonly-season-20261103-0315.png` zeigt Battle Modes, keinen Season-Banner/Kalender/Endtimer; „Results in 21h“ ist der Dream-Realm-Timer. `.spectre/afk-bot.lock` fehlt, Windows-Idle 6,14 s (<180-s-Gate); keine Game-Taps. T45j bleibt offen.
  🟨 Queue-Driver 03:34 CET 2026-11-03: MCP-`health`/`find` erfolgreich (BlueStacks + ADB erreichbar, Spiel-PID 4392). Read-only-Screenshot `.spectre/shots-4392/readonly-season-20261103-0334.png` zeigt erneut Battle Modes, keinen Season-Banner/Kalender/Endtimer; „Results in 21h“ ist der Dream-Realm-Timer. `.spectre/afk-bot.lock` fehlt; Windows-`GetLastInputInfo` meldet 0 s Idle (<180-s-Gate), daher keine Game-Taps. T45j bleibt offen.
  🟨 Queue-Driver 04:34 CET 2026-11-03: BlueStacks/ADB erreichbar, Spiel-PID 4392, AFK-Lock fehlt; Windows-Idle >180 s vor den sicheren Navigationstaps. Events → Stormbound Seas zeigt `Ends in 15d 20h`, aber nur Event-Quests/Claims (nichts geclaimt). Events → District Preview OCR bestätigt `Server District opens in 12d` und `Veil of Memories Season: September 23, 2026 - January 2027`; `Event Time: No Limit` gehört zum District-Preview-Event. `Season Modes Reset`-Infokarte nennt Updates, aber keinen Season-End-Tag/-Timer. Belege: `.spectre/shots-4392/readonly-season-20261103-043509.png` (Events), `...-043539.png` (Stormbound Seas), `...-043645.png` (District Preview/Seasonzeitraum), `...-043709.png` (Season Modes Reset). Zurück zum World-Screen; keine Belohnungen oder Ressourcen angefasst. Der sichtbare Januar-Zeitraum und der 15d20h-Eventtimer liefern keinen exakten Season-End-Cutoff; Scheduler-Arbitrage bleibt bis zu einem echten Season-End-Timer/Kalender-Timer offen.
  🟨 Queue-Driver ca. 06:12 CET 2026-11-03: Lock fehlte, Windows-Idle >180 s; MCP `health`/`find` bestätigten BlueStacks und PID 4392. Der Live-Check startete auf „Select Opponent“ nach dem Daily-Run; sichere Navigation blieb zwischen Arena-Lobby und Gegnerliste, daher kein Season-Kalender/Endtimer erreichbar. Kein Gegner-, Challenge- oder Claim-Button angetippt und keine Tickets/Belohnungen verbraucht. T45j bleibt blockiert bis ein echter Cutoff-Banner/Kalendertimer sichtbar ist.
  🟨 Queue-Driver 12:28 CET 2026-11-03: Live-Fenster (Idle 2208 s, Lock frei, Emulator via bluestacks-ensure gestartet). Events-Screen live gelesen: Golden Supplier 6d 12h, Routines 8d 12h, Stormbound Seas/District Preview/Baden Rate Up 15d 12h, Arcane Atelier 51d 12h. District Preview: „Server District opens in 12d“, „Veil of Memories Season: September 23, 2026 - January 2027“, Feature-Karten (Advancement Cap/One Tap Level Boost/Season Modes Reset) ohne Enddatum. KEIN exakter Season-End-Timer sichtbar — Arbitrage-Fenster (≤6 h) weit entfernt; nächster Check, wenn Stormbound-Seas-Timer unter ~2 Tage fällt oder ein Season-Cutoff-Banner auftaucht. Keine Claims/Käufe/Keys; Spiel sauber in WORLD zurückgelassen. Belege: .spectre/shots-readonly-122730.png (Events-Liste), -122800.png (Crescent Offering), -122830.png (District Preview).
- ✅ T45k: Supreme Arena Settlement-Slot wählerisch (12:00–24:00 UTC, 10-min-Fenster,
  15-min-Lockout letzte 30 min) → Off-Peak-Slot wählen (late-game Feature).
  ✅ Queue-Driver 03:4x: als operational Note in `docs/afk-journey-guide.md`
  (§ Free-economy edges) dokumentiert — Slot-Selektion = Scheduler-Slot-Problem,
  kein UI-Bot-Bedarf vor late-game. Off-game abschließbar, deshalb gezogen.
- ✅ T45l: Temporal Essence Swap: hero-spezifische Essence ↔ universal (Lucky-Flip-Picks
  nie tot). Notiz für Guide/Manuell — ✅ Queue-Driver 03:4x: Guide-Abschnitt in
  `docs/afk-journey-guide.md` (Swap-Richtung, +15-Unlimited-Regel, Bot-Regel:
  swap-to-universal als Default-Sink). Manueller Step bleibt (EX-Page).
- ⏸️ Nicht automatisieren laut Research: Gems für Attempts/Refreshes, Level-800-Stop
  (Stats flatten, Hourglass-Wert kollabiert).
### ✅ T45c-Update (03:1x): Chest-Popup verifiziert — kein separater Instant-Button
Das AFK-Chest-Popup hat EINEN Claim-Button (960,606). Die Daily „Claim Instant
AFK Rewards x1" dürfte durch diesen Claim abgehakt werden (Timing war exakt
nach dem Push, vor dem 05:00-Reset — der Guide-Tipp). Max Level ist auf
**Lvl. 95 gestiegen** (Stage-Fortschritt hebt den Level-Cap), Rates jetzt
+21180/h Gold (+3.3 % vs. T27-Zeitpunkt). Chest-Pending beim Claim: 127 Essenz,
41K Gold, 123K EXP, 1 Hourglass. AFK Progress 252→253.
Rest des Chest-Flows unverändert: Panel (60,1036) → Truhe (975,760) → Claim
(960,606) → Back. T45c gilt damit als abgedeckt durch den bestehenden Chest-
Claim (kein separates Feature nötig).
### ✅ T33-Feature: `scripts/afk_hero_level.py` — Leveling-Driver gebaut (2026-11-01)
Resonanz-Regeln bestätigt (Research): RL = niedrigste der 5 Hände; Levels in
höheren Händen kaufen accountweit nichts; Pre-240 RL kostet Gold+EXP+Essence,
**Gold ist der bindende Faktor bei Stage 254**. Policy umgesetzt: Gold/EXP/
Essence only, max 2 x10-Taps pro Hand pro Run, Abort bei unreadable/unknown.
Live: Hand 840 (Lv 84) erkannt + x10 gefeuert; Hand 1100 (Lv 74) erkannt,
x10 wirkungslos (Ascension/EXP-Limit?); Hände 710/970/1220 Detail-OCR leer
(Screen-State zu verfeinern). Rest-Punkte: (a) Post-x10-Screen-Wechsel brechen
den zweiten OCR-Read (Level-Animation/Confirm? — Screenshot-Analyse nötig),
(b) OCR-Parsing verfeinern (Power-Zahlen können als Level fehlgelesen werden),
(c) Resonance-Heroes stehen auf 74 trotz RL-80 (Widerspruch zum Rules-Panel —
aufzuklären). Danach: Push-Loop → neue Wand messen.

### ✅ T33-Rest: Resources-out-Detection + OCR-Retry (Leveling-Driver verifiziert)
Live (2026-11-01 03:4x): Hand 710 (Lv 74) → x10 → Level unverändert →
„resources exhausted, stopping run" + Top-up-Hinweis im Log. OCR-Retry bei
leeren Reads. Der Leveling-Driver ist damit produktionsklar: er levelt, bis
die Ressourcen ausgehen, und stoppt sauber. Wiederaufnahme: automatische
(Progress-Run 17:10) oder per Cron, sobald EXP/Gold nachgefüllt ist (Chest-
Claims liefern 123K EXP + 41K Gold pro Claim ~5 h).
Wand-Stand: Stage 254, Level-Cap 95, Resonanz 80. Die „Wand" bei 250 löst
sich durch Auto-Battle-Retries (249→252 gemessen) + Leveling. Der
Resonance-Heroes-74-vs-RL-80-Widerspruch bleibt beobachtungsrelevant.

## P9 — Agent-Infra & MCP (Hermes, 03.11.)

- ✅ T59: `spectre-mcp` (MCP-Server: Live-Pipeline als Agenten-Tools, einziger adb-Owner,
  serialisiert) — gebaut (Claude), unabhängig verifiziert (11 Tests, clippy 0, Live-Smoke
  health/find/regions/read/screencap gegen BlueStacks), in `main` gemergt (`13e959f`),
  Branch `feature/T59-spectre-mcp` gepusht. Nutzung via `.mcp.json` (projekt-scope):
  MCP-first, nie CLI+adb parallel.
- ✅ `scripts/bluestacks-ensure.sh` + Queue-Driver-Prompt: Emulator startet idle-gated
  selbst (Exit 4 = Idle-Gate) statt „Sergej startet manuell".
- ✅ Nach dem Wave-Merge nach `main`: `cargo build --release -p spectre-mcp -p
  spectre-cli` im main-Checkout — erledigt 2026-11-03 (Build 48 s, HEAD 32426be).
  Beide Binaries frisch (`target/release/spectre.exe` + `spectre-mcp.exe`, Nov 3
  11:49); `spectre.exe --version` = 0.4.0; MCP-Smoke über stdio (initialize mit
  den .mcp.json-env Werten) antwortete korrekt (serverInfo spectre-mcp 0.4.0).
  `claude mcp list`: `spectre: ...spectre-mcp.exe - ✔ Connected`. Der
  .mcp.json-Pfad ist damit real und healthy.
- ⬜ Optional (YAGNI): MCP-Tools für `search`-Refine (`--continue`) nachziehen.

---

## P8 — Manueller Code-Review (2026-11-03, Hermes) — Scheduler-Kette

> Anlass: 2 Tage BlueStacks-Ausfall; off-game Review der Scheduler-/Wrapper-Schicht.
> Alle HIGH/MED-Funde eingezogen (commits cde8ecd + 584ea2f).

- ✅ R1 [HIGH]: „Spectre AFK Night"-Task + Launcher existierten nicht, obwohl
  afk-night.sh geschrieben/dokumentiert war → .cmd/.vbs erstellt, Task
  registriert (02:00), E2E getestet (Exit-Code 2 propagiert, Lock-Cleanup ok).
- ✅ R2 [HIGH]: afk-night.sh behauptete „idle gate applies", uebergab aber kein
  --min-idle → Nachts-Push tippte bei PC-Nutzung. Verdrahtet.
- ✅ R3 [MED]: Daily-Phasen (dream realm, stage push) ohne --min-idle/--pid/
  --base → Mid-Run-Uebernahme wurde ignoriert. Verdrahtet.
- ✅ R4 [MED]: Arena-Tagesmarker wurde auch bei Fehlschlag gesetzt → kaputter
  Arena-Tag verbrauchte den Marker ohne Fortschritt. Jetzt nur bei Versuch-1-
  Erfolg (exhausted-Pfad returned 0 = Erfolg, korrekt).
- ✅ R5 [MED]: afk_arena.py hatte kein --min-idle → ergaenzt (Exit 5).
- ✅ R6 [LOW]: night.sh-Frühfehler gingen nur auf die versteckte Konsole →
  jetzt Tages-Log (wie watch.sh).
- ✅ R7 [HIGH, Deep-Think]: LOCK_STALE 1200 unterbietet die reale Worst-Case-
  Runtime (Daily-Runde >30 min, Night 2h+). Ein später Start hätte den Lock
  als „stale" geloescht und PARALLEL getippt. → Lock-Keeper (touch alle 240 s)
  in beiden Wrappern, LOCK_STALE 3600, Night auf 135 min gekuerzt (Ende vor
  dem 05:10-Daily).
- 📄 R10 [REVIEW-DOKU]: docs/reviews/2026-11-03-scripts-review.md — Subagent-
  Review (7 Skripte, frame-/live-verifiziert): u. a. arena-Kaufdialog-Probes
  50 px daneben (Gate feuert nie), battle_modes-False-Positive (Live-Ursache
  Arena-Fehler), hero_level-Parser-Defekte, wall-dash-Crashes, classify-Klippe,
  .spectre 1,3 GB + idle_seconds-Overflow. Als A7 (a/b/c) im Wave-2-Plan →
  Claude-Batch nach A1.
- 📄 R11 [REVIEW-DOKU]: docs/reviews/2026-11-03-runtime-review.md — Subagent-
  Review stage_push/dream_realm (artefakt-verifiziert): HIGH Fight-Start-Regress
  (schwarzer Frame = „läuft" → Chance verloren), wait-ohne-Re-Arm, LAUNCHER-
  Kreuzklassifikation, Screenshot-Leak 1,05 GB, Phantom-Wins u. a. Als A8 im
  Wave-2-Plan → Claude-Batch nach A1.
- ✅ R8 [MED]: Login-Popup („Esperia Monthly / Daily Rewards") — erledigt
  (7e80fb4): resolve_startup_popup() mit OCR-Gate, verdrahtet in Claim-Flow +
  Stage-Push; nie blind (nur OCR-erkannte Popups werden geclaimt).
- ✅ R9 [LOW, 2026-11-03 17:5x CET, Queue-Driver]: scripts/_level_hands.py
  redundant zu afk_hero_level.py → bereits ERLEDIGT durch den Wave-2-Batch
  A4/T48 (Report docs/reviews/../claude-wave-2-run.md §A4: Datei gelöscht in
  Commit `621451a`, F32 bestätigt; afk_hero_level nutzt die claim_vision-Helfer).
  Verifiziert: Datei existiert nicht mehr (`ls` leer), Repo-Suche nach
  `_level_hands` findet nur historische Docs (Wave-2/4-Reports, Review-Artefakte).
  Offener R9-Punkt war stale — geschlossen ohne Code-Change.
- ✅ R12 [LOW, 2026-11-03]: `afk-night.sh` now captures both `PIPESTATUS` values
  after `tee`, propagating the stage-push result (including idle SKIP=5) and
  surfacing a `tee` error when the push succeeds. Regression test
  `scripts/tests/test_afk_night_exit_code.py` was RED before the fix (fake push
  rc 7 became wrapper rc 0) and GREEN after (wrapper rc 7). No post-fix live
  Night run was forced; Task Scheduler result will verify on the next scheduled
  run.
- ✅ R13: Frame-Manifest-Regen nach dem Junction-Teardown — erledigt 2026-11-03 12:3x CET (Queue-Driver).
  `make_frame_manifest.py` plain Rebuild über die post-teardown Frames: 19 Einträge
  (vorher 139, alle auf gelöschte Dateien zeigend → Regression checkte 0). Suite:
  191 Tests OK (22 skipped); Frame-Regression jetzt `checked=19 skipped=0`.
  Manifest committet. Nach künftigen Live-Läufen (z. B. 17:10-Progress) erneut
  regenerieren, um frische Frames aufzunehmen (Verfahren: docs/agent-workflow.md).
  Beobachtung (nicht gefixt, Review-Kandidat): `classify()` liest den Arena-
  Select-Opponent-Screen als POPUP (dr_world_final, readonly-season-060730 —
  dunkler Hintergrund, Back-Probe 54/26/24); afk_arena nutzt eigene Probes,
  aber ein Dailies-/Claim-Flow an dieser Stelle würde „dismissen“. Für den
  nächsten Fresh-Eyes-/A-Batch queueen.
- ✅ R14 [2026-11-03, Review-Nachlauf]: Unabhängige Wave-2-Verifikation durch 2
  Fresh-Eyes-Agents: alle F1–F32 = FIXED (mit File:Line-Evidence), KEIN FAIL;
  Tests per Reversion-Experiment als scharf bewiesen (Fix zurückdrehen → genau
  die zugehörigen Tests fallen). In diesem Nachtrag behoben: Prune-Call-Test
  (Coverage-Gap), Trash-Fallback im Frame-Test (Manifest-Decay), Arena-Docstring,
  Report-Zahlen. OFFEN für nächsten Batch: F10-Rest (Zweitpixel-Probe; Recon),
  F25 (Lobby→PREP; Recon), N2/A8 (stage_push LAUNCHER-Kreuzklassifikation,
  dream start_fight-Fight-Marker + wait_re-arm). Live-Gegenproben: F1-Cancel-Tap
  (1014,710) auf echten row-729-Dialogen, F7-Chip-Marge (103 vs 100).
- 📌 R15 [2026-11-03]: A8 (R1–R18 Runtime-Fixes) gemergt (b330e6b) — 12-Punkte-
  Live-Check-Liste in docs/reports/claude-wave-2-a8-run.md §§. Beim nächsten
  Live-Fenster: F1-Cancel-Tap-Gegenprobe + F7-Chip-Marge (aus R14) + A8-Live-
  Checks (dream start/re-arm/chances, stage launcher/loading, popup-close,
  adb-down exit 2, summary-close). Danach Frame-Manifest-Regen (R13).
  🟨 Queue-Driver 12:3x CET: Teilbeobachtung zu F7 (read-only, Live-Frame):
  die Chip-Probe (1390,704) ist kameraabhängig — auf der aktuellen Homestead-
  Kamera liest sie (70,135,210) (blau, Gates chip>200/150/<120 verletzen) und
  der Fallback bleibt OFF, classify trotzdem WORLD über die anderen Probes
  (sicheres Verhalten: kein Fallback ≠ falsche Taps; deckt T30-Fund 2).
  F7 bleibt offen: eigentliche Marge-Messung braucht die Standard-Town-Kamera.
  🟢 F7-Datenpunkt 2 (16:4x CET, Queue-Driver, read-only, Standard-Welt nach
  BACK aus Dream): chip (1390,704) = (61,121,193), lum 111 — WORLD liest
  BLAU, chip[2]=193 verletzt die <120-Bedingung um 73 Einheiten; der
  PANEL-Fallback (orange ~240/191/52 nötig) kann auf Welt-Frames beider
  gemessener Kameras nicht false-firen. Marge damit ausreichend belegt;
  F7-Verhalten (Fallback bleibt OFF, classify WORLD über die anderen
  Probes) verifiziert — Rest F7 nur noch Dokumentationswert.
- 📌 R16 [2026-11-03]: Wave-3-Plan angelegt (docs/claude-wave-3-plan.md) —
  Zielbild Voll-Auto/Optimiert + Hacking-Lane (FPS/Frida/timeScale, Memory-Map,
  Sniffing, Uhrzeit) mit Safety-Matrix. Starter-Briefs C1–C5 (T61–T65) im
  Paste-Prompt docs/claude-wave-3-prompt.md. Research-Agents (Speed-Landschaft,
  Projekte/Exploits) laufen; Live-Recon L1–L8 in §5. Queue-Driver: B/H-RECON
  ziehen, wenn Blöcke gefüllt.
- ✅ R17 [2026-11-03]: A8-Reviewer-Urteil: 18/18 verifiziert (14 FIXED, 2 PARTIAL
  mit dokumentierter Begründung, 2 bewusste Abweichungen als sinnvoll bestätigt,
  kein HAND-WAVY; Reversion-Checks R1/R2/R9/R17 grün). Alle Rest-Concerns in
  DIESEM Batch geschlossen: R16 OCR-gated Fallback-Tap, R12 Stuck-Close-WARN +
  Recovery (jeder 10.), Dream-Prune pro Fight, Trash-Auto-Age (14 Tage),
  Start-Tap zählt ins Budget. 150 Tests grün. Live-Checks bleiben (R15).
- ✅ R18 [2026-11-03]: Wave-3-Starter-Review (Fresh-Eyes): KEIN FAIL — Merges
  sauber (keine Konflikte/Verluste), 36 neue Tests scharf (5 Reversionen alle
  gefangen), C2-C5 korrekt & sicher, Tests schreiben nichts nach .spectre.
  CONCERNs abgeräumt: C2 set_fps ersetzt jetzt ALLE Dup-Vorkommen (+2 Tests),
  .bak-Semantik dokumentiert. C5-Titel-Tap bleibt Live-Check (bounded, harmlos).
- ✅ C5-LIVETEST [2026-11-03 13:06]: device-ensure.sh live gefixt (MSYS-Pfad
  /c/... wurde an natives python als C:\c\... gereicht -> cygpath -m) und
  verifiziert: VM ok, Spiel-PID 5176 gefunden, WORLD erreicht, rc=0. Titel-Tap
  blieb diesmal ungetestet (Spiel startete direkt in der Welt).
- ✅ Wave-4 (D1–D4) [2026-11-03]: Zombei-Recovery (T66), Tages-Leveling-Regel
  (T67, exakt 1 Charge/Tag — T33 damit abgearbeitet), device-ensure-Verdrahtung
  (T68), Dura's-Trials v1 (T69). Alle 4 gemergt, 230 Tests grün. Live-Checks
  offen: LEVEL_X1 +1-vs+10, Dura's-Komplettnavigation, (480,300)-Karten-Dismiss,
  + 7er-Liste im Bericht docs/reports/claude-wave-4-run.md. Hinweis: T66-Nummer
  doppelt (feature/T66-tray-icon existiert in spectre-tray).
- 🟢 A8-Live-Checks Teil 1 (2026-11-03 15:0x CET, Queue-Driver, idle-gated,
  PID 5176, Guard 'ok' 259850): Dream-Flow live verifiziert — Fight 1
  (--fights 1) sauber: Re-Tap nach unverändertem Boss-Screen (R1-Rearm
  sichtbar im Log), `2x speed enabled` erst im Kampf (R6), `chances left
  = 7` stimmte mit der Anzeige (R7), Battle-Ended-Card resolved (R16-
  Pfad), Exit 0; Fight-Shots wanderten nach .spectre/trash (R8-Prune).
  Chance 7→6 verbraucht (Battle-Modes-Karte las 6/7).
  **A8-Live-Fund #1 (HIGH): `is_fight()` false-positive auf dem Battle-
  Modes-Screen** — Probes (960,1040)=(109,93,93) / (1280,1010)=(108,92,92),
  lum je ~97, weder weiß noch grün, kein Endzustand/Dim/Ready →
  is_fight=True bei classify=UNKNOWN. Folge: reach_world() an Entry
  wartet 150 s auf ein „laufendes Fight" und bricht ab (Exit 1; Beleg
  shots-77148/dr_world_0.png). Weil Battle Modes für classify() UNKNOWN
  ist und reach_world BACK auf UNKNOWN verweigert, kann das Script diesen
  Screen nicht selbst verlassen — ein Lauf, der auf Battle Modes endet,
  blockiert damit den Folgelauf. Fix-Kandidat für den nächsten Fix-Batch
  (NICHT inline): reach_world um is_battle_modes-Probe → BACK erweitern;
  ggf. is_fight zusätzlich auf das Battle-Modes-Layout negativ gateen.
  Workaround heute: manueller BACK (474,1010) aus Battle Modes → WORLD
  OCR-verifiziert → Re-Run grün.
  **Op-Notiz:** Dream-Läufe >3 min nie foreground starten (180-s-Clamp
  killt das Script mitten im Kampf — live passiert: Chance verbraucht,
  Ergebnis unresolved; der In-Game-Fight lief autonom weiter, der Re-Run
  übernahm den Ready-State sauber über back_to_ready) → background+poll.
  Dream-Stand heute: 3/7 Chances verbraucht (2 completed verifiziert + 1
  beim Timeout-Kill gestartet); Rest beim nächsten idle-gated Fenster —
  Boss-Page „King Croaker, Elite Challenge, Highest Damage 1,076,922"
  steht bereit (Beleg shots-77148/readonly-state-1513.png); der direkte
  Re-Run dazwischen SKIPpte korrekt (Idle 63 s, Exit 5).
  R13-Manifest-Regen (Teil 2 von R15): plain Rebuild → 28 Frames (vorher
  19), Frame-Regression `checked=28 skipped=0`, Gesamtsuite 230 Tests OK
  (22 skipped). Manifest committet.
- 🔴 A8-Live-Fund #2 (15:35 CET, HIGH): **is_boss_page false-positive auf
  dem Helden-Detail** — der vollbreite grüne „Level Up"-Balken trifft beide
  Green-Probes ((960,1040) + (1280,1010)) → is_boss_page=True → run() liest
  das Detail als „already inside Dream Realm" und start_fight feuert
  BOSS_TAP (960,1020) 4× AUF DEN LEVEL-UP-BUTTON (kein Chance-Verbrauch,
  Fight startete nie; Exit 1 „did not start after 4 battle taps"; chances
  „unreadable" — auf dem Detail gibt es keinen Counter). Beleg:
  .spectre/shots-62080/dr_f1_pre3.png (Cecia Lv 84, Level-Up-Balken) +
  dr_f1_after3_5.png (Lv 85).
  ✅ FIX EINGEZOGEN (15:4x, Commit d50c601): `is_hero_detail()`-Gate in
  is_boss_page — Probes Ascend-Plate (620,992) + Back-Arrow-Plate
  (466,1014), beide >190 lum auf 2 echten Helden-Details
  (Cecia/Gwyneth), auf der echten Boss-Page dunkel/blau (25,49,118 /
  87,150,199 — King Croaker, shots-77148). Bright-Background-Boss-Pages
  würden fail-safe abbrechen (kein Chance-Verbrauch, keine Blind-Taps).
  Bonus: der Gate behebt den GLEICHEN latenten False-Positive auf der
  Arena-Lobby (shots-51424/arena_1_lobby: boss_green=True). 3 neue Tests
  (R20); Gesamtsuite 235 Tests, 4 Failures — alle 4 aus dem UNCOMMITTETEN
  Parallel-Writer-Stand afk_hero_level.py (HALL_BTN 972→990 bricht 3
  test_flows-Assertions; LEVEL_X10==LEVEL_X1==(1100,985) bricht
  test_daily_leveling) — in-flight, NICHT vom Dream-Fix. Live-Verifikation
  des Gates steht beim nächsten Dream-Retry aus.
- 🔴 Op-Fund Race (15:31–15:35 CET, HIGH): **Direkte Script-Läufe nehmen
  den afk-bot.lock NICHT** — der Lock schützt nur watch.sh-Wrappers. Live
  kollidierte der Dream-Lauf (shots-62080, 15:31:5x) mit der aktiven
  Wave-4-Leveling-Livecheck-Session (.spectre/livecheck/: aftertap.png
  15:31:59, detail710/cecia2, after_charge 15:28:59, after_confirm
  15:32:54; weitere zz_probe-/hl_entry-Shots bis 15:34:53) — beide tippten
  auf denselben Helden-Detail-Screen. **Policy-Notiz für Sergej:** im
  Kollisionsfenster gingen Level-Up-Taps aufs Cecia-Detail (Lv 84→85
  sichtbar; Zuordnung Queue-Driver-Taps vs. Livecheck-Session nicht
  rekonstruierbar) — das kann zusätzliche x1-Level-Ups neben der T67-
  1-Charge-Regel bedeutet haben; keine Käufe/Keys/×4, nur freigegebenes
  Gold/EXP-Leveling. Fix-Kandidaten: (a) Lock-Acquisition IN den Skripten
  (afk_dream_realm/afk_hero_level/afk_claim_vision-Flows), (b) Driver-
  Regel: vor jedem Tap-Fenster auf frische fremde shots-Dirs (<2 min)
  prüfen und abwarten. Dream-Retry ÜBERSPRUNGEN, solange der Livecheck-
  Writer aktiv ist (Idle 0 s, hl_entry 15:34:53) — Chances 4/7
  unverbraucht, Boss-Page „King Croaker" steht weiter bereit.
- ✅ Race-Fund-Fix (a) abgeschlossen + Dream-Retry nachgeholt (16:19–16:37
  CET, Queue-Driver, idle-gated): (1) Lock-Wiring jetzt auch in
  `afk_hero_level.py` — der Parallel-Writer hat den Stand committet
  (1504750), Gate sitzt VOR dem Hall-Tap, Exit 7 dokumentiert; Wiring-Test
  erweitert (hero_level in der gated-Liste + Gate-Reihenfolge-Check,
  Anker „# navigate:" statt v.tap(HALL_BTN — der Helper in_hall tippt
  denselben Button später, erster Index wäre falsch). Suite 246 Tests OK
  (22 skipped). Live: Exit-7-Pfad mit Fremd-Fresh-Lock bewiesen (SKIP-Zeile,
  0 Game-Taps, Lock sauber entfernt), Commit 3084384. Damit sind ALLE 5
  direkt-laufbaren Entry-Points gelockt — der afk_hero_level-Caveat in
  docs/agent-workflow.md ist gegenstandslos. (2) Dream-Retry: 4/4 Kämpfe
  sauber (wall 109.8/98.0/110.2/109.8 s, mean 107 s), Chances 4/7 → 0/7
  (Battle-Modes-Karte liest ×0/7), Exit 0; Endzustand Battle-Modes-Menü,
  read-only verifiziert. Dream Realm heute 7/7 erschöpft. (3) A8-Live-Fund
  #1 (reach_world blockiert auf Battle Modes) ist im gemergten A8-Stand
  BEREITS gefixt (is_fight-Negativ-Gate + reach_world-BACK, Docstrings
  zitieren den Fund) — TODOS-Vermerk „Fix-Kandidat" überholt; LIVE
  bewiesen: `--fights 0`-Run startete AUF Battle Modes, loggt
  „dr_world: Battle Modes menu -> BACK (A8 fund #1)", erreicht WORLD →
  Dream → Exit 0 (kein Chance-Verbrauch). Dry-Run nach dem 0-Fight-Exit:
  boss=True/ready=True = Dream-Boss-Page, der Folgelauf nimmt
  „already inside Dream Realm" — UNKNOWN ist nur das classify-Label,
  kein Blocker. Rest R15: F1-Cancel-Tap-Gegenprobe, F7-Chip-Marge
  (braucht Standard-Town-Kamera), Stage launcher/loading, adb-down
  Exit 2, summary-close.
  🟨 F1-Gegenprobe-Versuch 16:5x CET (Queue-Driver, idle-gated, Endzustand
  WORLD wiederhergestellt): Arena-Attempts live > 0 — Schwert-Tap (760,810)
  auf Select-Opponent ging DIREKT auf die Prep-Seite (kein Kauf-Dialog);
  der 'Spend diamonds?'-Dialog (row 729) ist nur bei Attempts = 0
  produzierbar. Probe verschoben bisfenster: nach dem Tages-Arena-Verbrauch
  des Bots ODER wenn ein Run-Log natürlich ein CONFIRM-Abfangen zeigt
  ('Turn off Auto Battle?' im Stage-Push — 17:10-Run liefert evtl. Evidenz).
  Kein Kampf verbraucht, kein Kauf, Prep nie bestätigt (BACK-Pfeil auf
  Select-Opponent sitzt bei (714,1010), nicht bei BACK=(474,1010) — nur
  Recherche-Notiz, afk_arena nutzt BACK nicht im Fight-Chain).


- 🟢 **17:10-Progress-Run (erster Post-Fix-Livebeleg) + Guard-Korruptions-Fund & Fix
  (Queue-Driver, 17:12–17:16 CET):**
  Der Progress-Run lief sauber: Chest-Claim verifiziert (Popup zu, Panel zurück),
  Stage-Push WORLD→AFK_PANEL→PREP→BATTLE, x2 enabled, DEFEAT nach 28 s → Night-
  Retry → „wall reached: 2 fights skipped in 41s" (wall_report stage=254
  power=74986), Task-Scheduler Last Result 0, Lock sauber entfernt. Beobachtung:
  das Spiel blieb auf der Stage-PREP-Seite stehen (Endzustand des Pushs; nächste
  Flows klassifizieren PREP und navigieren selbst zurück — kein Blocker).
  **🔴 Guard-Fund (HIGH): team_power-Anker um 17:10:18 korruptiert.** watch.sh
  pickt den GRÖSSTEN anonymen rw-Heap (0x7-space) — ein neuer 256-MB-Heap
  (0x796590000000) verdrängte den alten 194-MB-Heap (0x7964E0000000) ohne
  Game-Restart (PID 5176 unverändert). Der Preflight-'ok'-Branch prüfte nur die
  globale Plausibility-Range (GUARD_HI = 1e10) und akzeptierte den Garbage-Read
  108449240 am selben Offset im neuen Heap → Anker still überschrieben.
  Evidenz: alter Slot (0x7964E0000000+0x1BD838) liest WEITERHIN exakt 259850 mit
  intakter Map-Entry-Struktur ([u32 value][u32 hash][ptr]); neuer-Heap-Slot
  (0x796590000000+0x1BD838) liest 108449240 mit NUR Nullen dahinter (keine
  Map-Entry-Struktur) und passt zu keinem bekannten Power-Wert (12:47-OCR: 259K).
  **Fix (Commit in diesem Lauf): Drift-Gate im 'ok'-Branch** — gelesener Wert
  muss zum letzten verifizierten Anker passen (±max(2000, 10 %)), sonst Stale-
  Pfad (Re-Location mit Struktur-Checks + Anker-Fenster) statt stiller
  Anker-Korruption. 3 neue Tests (TGuardDriftGate); Gesamtsuite 249 OK
  (22 skipped). Anker-Datei restauriert + Live-Gegenprobe: Preflight am neuen
  Base Re-Location → **('ok', 259270)** via u64-Kandidat Offset 0xA73D14
  (≥2 Kopien, Δ 580 = 0,2 % zum Alt-Anker — plausibler Drift durch heutige
  Level-Ups; zwei unabhängige Strukturen [alter Map-Entry 259850, neue u64-
  Kopien 259270] bestätigen sich gegenseitig), Zweit-Preflight 0,1 s 'ok',
  Werte über 8 s stabil. Guard damit wieder scharf UND gegenüber Heap-Base-
  Rest R15: F1-Gegenprobe window-abhängig; Stage launcher/loading + summary-close
  brauchen entsprechende Übergangs-Frames; **adb-down Exit 2 inzwischen LIVE
  verifiziert** (siehe R15-Adb-Down-Note am Dateiende, 18:0x CET).
  **Re-Check 17:35 CET (Queue-Driver, rein read-only):** Drift-Gate-Fix post-live
  bestätigt — Task-Scheduler: Daily 05:10 Result 0, Progress 17:10 Result 0,
  Night Ready → 04.11. 02:00; Idle 4774 s, kein Lock, kein aktiver Parallel-
  Writer (letzte shots 17:15/17:16 = eigener Run). `pidof` = 5176; Direkt-Reads:
  alter Slot (0x7964E01BD838) liest unverändert 259850 mit intakter Map-Entry-
  Struktur; neuer-Heap-Slot liest exakt **259270** = State-File-Anker (offset
  10960148, width 8) — Guard auf dem 'ok'-Pfad, kein Re-Location nötig.
  **Korrektur:** die TODOS-Notiz oben nannte den Offset fälschlich 0xA7594 —
  erneut ein Hex-Rechenfehler (dezimal 10960148 = 0xA73D14, Python-Check);
  dritter derartiger Fehler in dieser Datei (nach 0x1BD518). Regel: Hex-Werte
  in TODOS immer via `python -c "print(hex(...))"` verifizieren, nie mental.
  `scripts/_idle_probe.ps1` (untracked Helper aus dem 17:12-Lauf, verifiziert
  IDLE_SECONDS-Ausgabe) als Utility committet.

### ✅ Race-Fund-Fix (a): Tap-Lock in den Skripten — 2026-11-03 16:0x CET, Queue-Driver
- Neues `scripts/_bot_lock.py`: PID-guarded Acquire/Release auf `.spectre/afk-bot.lock`
  mit denselben Semantiken wie die Wrapper (R7): Fresh-Lock (< AFK_LOCK_STALE,
  Default 3600 s) → `acquire()=False` → Script **exit 7** („another bot run is
  tapping“) VOR jedem Probe/Tap; Stale-Lock → Takeover (wie die Wrapper);
  `release()` löscht nur den EIGENEN PID-Eintrag (niemals einen Wrapper-Lock).
- Verdrahtet in die 4 direkt-laufbaren Entry-Points: `afk_dream_realm` (main,
  vor Idle-Check), `afk_arena`, `afk_stage_push`, `afk_dailies` — jeweils
  `acquire()` → bei False Exit 7 + `describe()`-Zeile (Owner-PID + Age im Log),
  sonst `release_at_exit()` (atexit, PID-guarded).
- **Wrapper-Bypass:** watch.sh + afk-night.sh exportieren nach dem Lock-Erwerb
  `AFK_BOT_LOCK_HELD=1` — Kind-Scripts skippen die Acquire (die Wrapper
  serialisieren bereits); ohne das würden sie im Wrapper-Run selbst exit 7.
- **`afk_hero_level.py` bewusst NICHT verdrahtet** — uncommitted Parallel-Writer-
  Stand (tabu). Follow-up, sobald der Writer committet hat. Bis dahin gilt für
  Leveling-Läufe weiterhin die Driver-Regel (frische fremde shots-Dirs prüfen).
- Tests: `scripts/tests/test_bot_lock.py` (9 Tests: Semantik free/fresh-refuse/
  stale-takeover/Custom-Stale/Wrapper-Bypass/release-PID-Guard/describe +
  Wiring-Source-Checks für 4 Scripts + 2 Wrapper). Harness-Isolation:
  `fake_vision.py` leitet `_bot_lock.LOCK` in ein Temp-Dir UND stubbt das Gate
  (Originale als `_real_*` gesichert) — sonst leakt ein acquired Lock in
  Folgetests desselben Suite-Prozesses (live erlebt: 24 False-Failures rc 7).
- **Live verifiziert (read-only, keine Game-Taps):** Dry-Run mit freiem Lock →
  Probes laufen, Exit 0, Lock nach Exit weg; Dry-Run mit fremdem Fresh-Lock →
  Exit 7 + SKIP-Zeile für alle 4 Scripts, kein Probe/Tap; Wrapper-Bypass
  (`AFK_BOT_LOCK_HELD=1`) → Dry-Run läuft trotz Fresh-Fremd-Lock, Fremd-Lock
  bleibt bestehen. Suite: 245 Tests, 3 Failures — nur der bekannte uncommit-
  tete Writer-Stand afk_hero_level.py (HALL_BTN 972→990); test_daily_leveling
  ist inzwischen grün (Writer hat nachgezogen).
- Rest offen: Live-Gegenprobe im echten Kollisionsfall (z. B. 17:10-Progress-
  Run vs. direkter Driver-Lauf) — das Gate verifiziert sich im Betrieb.
- 🟨 Re-Check 16:02 CET: Writer weiterhin aktiv (2 PNGs nach 15:50 in
  shots-74688), Idle 71 s → Dream-Retry (Chances 4/7, Boss-Page King Croaker)
  weiter ausgesetzt. Read-only-Dry-Run las den aktuellen Screen als POPUP
  (Livecheck-Nachwehen); keine Taps.
- ✅ R19 [2026-11-03]: Wave-4-Review (Fresh-Eyes): KEIN FAIL — 25/33 Reversionen
  gefangen, Merges/Sentinel/Suite sauber. 4 CONCERNs = reine Test-Lücken (klein,
  offen): dream cycles-Pin, arena In-Chain-Dialog-Return, ensure-timeout-Pin,
  duras Sweep/Challenge/No-Token-Gates, daily 2-Lauf-Gate.
- ✅ D2-LIVE-VERIFIKATION [2026-11-03]: Leveling-Pfad live durchverifiziert und
  gefixt: HALL_BTN (990,1010 — gemessen), LEVEL_X1/Z10 (1100,985), Zwei-Tap-
  Sequenz (Tap1 oeffnet Preview-Panel 'Level N » N+1', Tap2 bestaetigt),
  slot_level() per Region-Crop (rechte Zahl; live 80->81 bestaetigt), blocked-
  Skip ('within 10 levels' -> naechste Hand). E2E-Lauf: 'charged: hand 1220
  level 80 -> 81'. Manuell+auto heute 2 Level verbraucht (Cecia 81, Slot 1220 81).

### ✅ R15 adb-down LIVE verifiziert (2026-11-03 18:06–18:12 CET, Queue-Driver)
- Checklist-Punkt 10 („adb weg → Exit 2 'adb down', kein FATAL"): Mid-Run-Test
  im freien Fenster (Idle 6796 s, Lock frei, kein Parallel-Writer — neueste
  shots-Dirs 17:15/17:16 = eigener 17:10-Run). `afk_stage_push.py --pid 5176
  --base 0x796590000000 --auto --auto-minutes 1` gestartet: Preflight 'ok'
  259270, initial PREP, Auto-Battle gestartet, x2 enabled — dann
  `adb disconnect 127.0.0.1:5555` mitten im Lauf (18:08:26). Ergebnis:
  5× `WARN: shot failed ... [n/5]` → `ERROR: adb down — 5 screenshots in a
  row failed` → **Exit 2**, kein FATAL-Traceback; Lock per atexit sauber
  entfernt; `adb connect` stellt das Device wieder her. Beleg:
  .spectre/shots-adbtest/adbdtest-run.log (RC=2) + pre/post/cancel-Shots.
- Varianten-Notiz: getestet ist Host-Disconnect (screencap → „device not
  found") — derselbe Failure-Pfad wie ein BlueStacks-Stopp (adbd weg,
  ADB_FAIL_CAP-Zähler in try_shot). Vollständiger VM-Stopp mid-Kampf nicht
  erzwungen (unnötig destruktiv, identischer Code-Pfad).
- ✅ R13-Manifest-Regen Teil 3 (2026-11-03 18:2x CET, Queue-Driver): plain Rebuild
  über die frischen Live-Frames (17:10-Progress-Run shots-77760 inkl. sp_world/
  sp_auto_confirm/sp_retry/sp_wall_report + adb-Down-Test shots-adbtest +
  Dream-Recheck/Leveling-Run-Verzeichnisse) → 48 Frames (vorher 42), Frame-
  Regression `checked=48 skipped=0`, Gesamtsuite 249 Tests OK (22 skipped).
  Diff geprüft: 0 Verdict-Flips auf gehaltenen Frames (reiner Frame-Set-Refresh:
  34 neue Frames, 28 Pfade verworfen = inzwischen gelöschte Dateien). Manifest
  committet. Bonus: der Markt enthält jetzt einen echten LOADING-Battle-Frame
  (shots-70956/f1probe_after_sword) — R15-Rest „Stage LOADING" hat damit
  offline Regression-Abdeckung; LAUNCHER + Summary-Close bleiben Frame-abhängig
  offen. Keine Game-Taps nötig (Idle 7946 s, Lock frei, kein Parallel-Writer).
- Anker-Sicherheit: memory_preflight schreibt bei ADB-Ausfall NICHTS
  (read_power → None → 'fail', kein save_power_state); State-File nach dem
  Test unverändert 259270/offset 10960148/width 8 (updated 18:08:07 durch
  den eigenen 'ok'-Preflight VOR dem Disconnect).
- Nachbereitung: der Kampf lief während des Disconnects autonom weiter und
  endete → „Turn off Auto Battle mode?"-Dialog → CONFIRM_CANCEL (1014,710)
  getippt (dokumentierter Cancel, nie confirm) → Spiel endet auf dem
  DEFEAT/Retry-Screen (Wand-Kontext Stage 254, Power 74,986). Kein Kauf,
  keine Keys, kein Leveling, kein Retry angetippt.
- Rest R15: F1-Gegenprobe weiterhin window-abhängig — Arena heute „0 fights
  driven" (Log 04:12Z, Versuche NICHT verbraucht) → „Spend diamonds?"-Dialog
  nicht produzierbar, Gegenprobe erneut inkonklusiv. Stage LAUNCHER/LOADING +
  Summary-Close brauchen die jeweiligen Übergangs-Frames (dieser Test-Run
  startete auf PREP, produzierte keine).
- ✅ F1 gelöst + exit_to_world (2026-11-03 19:4x CET, Queue-Driver):
  Arena-Attempt-Mechanik live aufgeklärt (Idle-Fenster 10885 s, Spiel PID 5176):
  Battle-Modes-Karte „Arena ×2/4“ = Versuche übrig, konsistent mit dem orangen
  Lobby-Medaillon (Stand 2 nach den 3 Kämpfen des 19:14-Laufs: 5-frei/Tag
  (T45e) minus 3; Token-Beweis 1200 → 2100 = 3 × 300). „Spend
  diamonds?“-Dialog nur bei Medaillon-Stand 0 produzierbar (+-Button =
  Diamanten-Kauf, tabu). Season-UI live: Lobby-Hauptbutton „Continue“ mit
  Countdown (läuft auf 00:00 UTC = Arena-Settlement, T45k), Position
  (1080,1004) + grüner Lobby-Probe unverändert — keine Codeänderung nötig.
  exit_to_world() in scripts/afk_arena.py (Commit 30d67b8): bounded
  5 Steps, WARN-only, RESULT-Dismiss + PREP- (live shots-78504: nach dem
  letzten Kampf steht das Spiel auf der Arena-PREP-Seite; BACK 474,1010 →
  Select) + positive-SELECT-Erkennung vor dem Lobby-Probe (Badge 1160,1010);
  Route Select → (714,1010) → Lobby → (474,1010) → Battle Modes → (474,1010)
  → World, ohne Attempt-Verbrauch. E2E-Live-Run: Fight sauber (changed=True,
  Wall 84,7 s, Exit 0). Suite 252 OK (22 skipped), 3 neue Exit-Tests +
  aktualisierte Frame-Listen. Offen bleibt R15-Rest: Stage LAUNCHER/LOADING +
  Summary-Close-Frames; erster Post-Fix-Night-Beleg 04.11. 02:00.
- ✅ R13-Manifest-Regen Teil 4 + Log-Review (2026-11-03 19:4x–20:0x CET,
  Queue-Driver): Manifest-Regen über die neuen Arena-Frames (shots-78504 Exit-
  Kette Select/PREP/Lobby/BattleModes/World) → 62 Frames (+14, 0 Verdict-Flips,
  0 verworfen), Suite 252 OK (22 skipped), Commit 35951a3. exit_to_world
 Commit 30d67b8 + TODOS-Notiz d044ca2 (Suite davor verifiziert: 252 OK).
  Log-Review afk-bot-2026-11-03.log: 05:10-Daily zeigte die bekannte
  Endzustand-Verschmutzung (Arena 0 fights/STUCK → Dream POPUP → Stage
  „not on battle screen“) — exakt das, was positive-SELECT-Probe (ff6ad3d)
  + exit_to_world (30d67b8) abdecken; erster Post-Fix-Beleg: Daily 04.11.
  05:10, Night 04.11. 02:00. 17:10-Progress: sauber (Chest verified, wall
  reached stage=254 power=74986); „preflight 108449240“ in der Logzeile =
  Vor-Fix-Stand, Drift-Gate 80b8b43 fängt den Fall seit 18:08 ab (Anker
  259270 revalidiert).  R15-Rest unverändert: Stage LAUNCHER/LOADING +
  Summary-Close-Frames sind frame-abhängig offen.
- 🟢 Drift-Gate erster Natural-Drift-Beleg (2026-11-03 20:17 CET, Queue-Driver,
  rein read-only): Idle 14616 s, Lock frei, PID 5176; neuer-Heap-Anker
  (0x796590000000+0xA73D14, u64) liest **259176** (Δ 94 zum Anker 259270 —
  legitimer Power-Drift, Map-Entry-Struktur intakt; alter Slot liest weiter
  259850). `memory_preflight('5176','0x796590000000')` → **('ok', 259176)**
  — der 'ok'-Branch akzeptiert den Drift innerhalb ±max(2000,10 %) und
  aktualisiert den Anker (State-File updated 20:17:37). Damit ist der
  Drift-Gate-80b8b43-Pfad (akzeptieren) UND der Stale-Pfad (Re-Location,
  18:08-Live-Test) live belegt. Quirk dokumentiert: ein einzelner
  `dd bs=1`-Read am Anker kam transient als 00 00 00 00 zurück (Wiederholung
  las sauber) — Preflight-Guards decken das ab (Range + Struktur), keine
  Code-Änderung. Suite 252 OK (22 skipped). Keine Game-Taps. Nächste
  Post-Fix-Evidenz: Night 04.11. 02:00, Daily 04.11. 05:10.
- 🟢 Drift-Gate Pfad #3 live belegt (2026-11-03 20:49–20:53 CET, Queue-Driver,
  rein read-only): Idle 16577 s, Lock frei, PID 5176, kein Parallel-Writer.
  Der bisherige u64-Anker-Slot (0x796590000000+0xA73D14) liest jetzt
  `ec 55 04 00 0d 00 00 00` (284140 + High-Dword 13 — kein sauberes Power-u64
  mehr, Heap-Churn hat den Slot umgeschrieben). `memory_preflight` verwarf das
  (Struktur-/Range-Check) und re-lokalierte OHNE Game-Restart: erster Kandidat
  0xA67014 erwies sich als kurzlebige Display-Copy (<1 min — spectre-dump
  Gegenprobe las dort bereits Müll), zweite Re-Location fand den stabilen Slot
  **Offset 0xA67A54 (10910292, u64) = 259160** (Δ -16 zum Alt-Anker 259176,
  legitimer Drift), dreifach verifiziert (read_power + 2× preflight 'ok' +
  Direkt-Dump `58 f4 03 00 00 00 00 00`). Damit belegt: accept-drift (20:17),
  Stale→Re-Location nach Restart (18:08) UND Struktur-gebrochener 'ok'-Slot →
  Re-Location ohne Restart (dieser Lauf). Beobachtung (Review-Batch-Kandidat,
  kein Inline-Fix): die u64-Anker-Slots im neuen Heap churnn offenbar im
  Minutentakt — jeder Preflight zahlt dann ~30 s Re-Location; der u32
  Map-Entry im ALTEN Heap (0x7964E01BD838, liest weiter stabil 259850) ist
  die strukturell stabilere Kopie — Kandidat: Revalidator bevorzugt
  strukturstabile Slots. Kein Code-Change in diesem Lauf. Ein weiterer
  mentaler Hex-Slip (0xA68114 statt 0xA67A54) rechtzeitig durch den
  Python-Check gefangen — Regel bleibt: nie Hex mental rechnen.
- 🟨 T72-LIVE-Befund [2026-11-04 00:3x]: HAND_XS-Neusatz + Scan-Retry live
  geprüft — alle 5 Slots erreichbar (Reads kamen nach Retry), Retry bounded +
  geloggt OK. OFFEN (an Wave-5/T80b gebrieft): Timing-Race im Charge-Pfad —
  nach Hand-Tap ersten Read 4/5x None; bei Hand 1090 las der pre-Read noch den
  ALTEN Wert (85) des Vorgänger-Details -> 'no effect'-SKIP. Fix: bounded wait
  bis is_detail statt fixe 3 s. Tagescharge 04.11. unklar; 05:10-Daily läuft eh.
- ✅ R20 [2026-11-04 01:3x]: Wave-4.5-Review (Fresh-Eyes): ALLES OK — 4 Test-
  Reversionen + 10 Logik-Mutationen alle gefangen; E1 deckt die 5 Lücken exakt,
  E2-Lock-Verhalten scharf (rc7 ohne Shot/Tap, Bypass, Stale-Takeover), E3-
  Retry genau-1x, E4-Mapping exakt (14 Tools, clippy clean @ da970... @20da970),
  Suite 288 OK, .spectre schreibfrei (mtime-Snapshots). Keine offenen Punkte.
- ✅ W5-LIVE-TEIL [2026-11-04 02:2x]: T77 read-batch + T78 afk_memory live
  verifiziert — 'afk_memory --show' => 'team_power: ok 258488' (Drift-Re-Location
  greift am echten Gerät; neue ASLR-Base 0x796590000000, Wrapper-Regel liefert
  sie dynamisch; yaml-Position stale -> Guard relokalisiert). ZWISCHENFALL+REGEL:
  adb-Serial 127.0.0.1:5555 kann nach HD-Adb-Kontakt (Server-Version-Konflikt
  v36 vs v41) verschwinden -> `adb disconnect 127.0.0.1:5555 && adb connect
  127.0.0.1:5555` reaktiviert (kein kill-server). Release-Binary neu gebaut
  (read-batch vorhanden). Rest-Live offen: T75/76 im Feld, T80 frida (rc3 ohne
  frida), mem_probe-Praxislauf.
- ✅ R21 [2026-11-04 03:3x]: Wave-5-Review (Fresh-Eyes): kein FAIL — 7/7
  Reversionen gefangen; live gegengeprueft (raw-Shot 2,1s vs 2,4s PNG; read-batch
  byte-identisch zu dump; power() ok 258488). 3 CONCERNs GEFIXT: mem_probe
  SCAN_TIMEOUT 300->1200 (reale Scanzeit gemessen 13m39s), hot-WARN/ANSI-Prefix
  toleriert (+Test), read-batch note-Dedupe (+Assert). Praxislauf gestartet.
- ✅ Wave-6 (F1–F5) [2026-11-04 ~04:3x]: afk_memory-Rollout, Region-OCR-Rollout,
  tap_seq II, Dura's im Daily, speed_profile ops-ready. 5 Merges konfliktfrei
  (d2ec11d), Delta-Suite 379 OK, Release-Build unnoetig (kein Rust). Worktrees
  entfernt. Erst-Review via headless claude -p laeuft (Token-Regel). Live-Checks:
  docs/reports/claude-wave-6-run.md.
- ✅ R22 [2026-11-04 03:55]: hero_level-Daily-Fix (2 Live-Bugs aus dem Charge-SKIP):
  (1) slot_level-Box las im Detail den Resonanz-CAP ("Level 100") statt des Held-
  Levels -> read_level (Lvl-Badge) hat jetzt Vorrang an allen Detail-Lesestellen
  (+Test: cap 100 leakt nicht; Mock-LIFO-Falle dokumentiert). (2) resources_ok
  verlor das K-Suffix der Bedarfszahl ('8138K/9360' -> 8.1M vs 9360) -> Suffix-
  Erbung (+2 Tests). LIVE bewiesen 03:55: scans alle 5 Hände lesbar (read_level
  robuster), before=82, "resources short ... no charge today" rc4 OHNE Taps.
  OFFEN: echte +1-Charge (Gold 8138K < 9360K) — nach Gold-Zuwachs (Daily).
- ✅ R23 [2026-11-04 04:05]: Wave-6-Review (headless claude -p, Token-Regel): kein FAIL.
  Merge-Integritaet OK, F1-F5-Checks OK, 12/12 Mutationen gefangen, 9/9 F2-Frames
  gleiches Urteil, Suite gruen, .spectre schreibfrei. 1 CONCERN (4b) GEFIXT: _run_seq
  jetzt &&-gejoint (Fehler nicht mehr verschluckt), LIVE bewiesen: Bruchteil-Sleeps
  (frac-ok) + tap_seq-Smoke ok; Test-Erwartungen nachgezogen.
- mem_probe-Praxislauf [04:05]: Mechanik live gruen (scan1 12 matches, scan2 1, sauberes
  rc3 "no candidate") — Kandidat fehlte, weil die Charge ausfiel (Gold short). Wiederholung
  sobald Gold reicht — dann Wert-Paar exakt vorab bekannt.
- ✅ R24 [2026-11-04 04:1x-05:1x]: Dura's-Entry LIVE untersucht (2 Fixes, 1 Befund):
  GEFIXT+live bewiesen: (1) classify() WORLD-Praedikat war fuer die Nacht-Schneewelt
  gebrochen (lb-lg +14.8 > alte |..|<8; live: reach_world tappte 6x sinnlos) -> Range
  -8..+25, 199-Frame-Sweep: nur die 7 echten Welt-Frames kippten. (2) is_battle_modes-
  Pixel waren verschoben (Tab-Leiste -26px, Events-Icon weiter rechts) -> neu
  kalibriert, live: Menue oeffnet+erkennt (3 true, 0 false auf 199 Frames).
  BEFUND: 'Dura' fehlt im Battle-Modes-Menue (alle 3 Sub-Tabs geprueft, Liste
  vollstaendig: Stage/Realm/Arena/LT/AL/HD + Coming-Soon: Supreme League + 2 leere
  Slots) -> auf H143 offenbar noch nicht freigeschaltet. AdbAutoPlayer (MIT-Ref)
  bestaetigt: Karte existiert, holt sie per kurzen Swipes (y1200->700, max 4) und
  hat 'not available yet (Coming Soon) skip'. NAECHSTES wenn Karte erscheint:
  Swipe-Loop + Kartenposition live messen; DURAS_CARD dann justieren.
- ✅ T86-T90 [2026-11-04 11:20-13:55]: Erkennungs-Schicht live gehaertet (Auftraege an
  Claude-Session; Hermes nur Live-Vermessung): T86 Intro/Welcome-Screen (Daily-Stopper),
  T87 Dura-Entry soft+swipe, T88 AFK-Panel-Palette, T89 Tag-Welt vs POPUP (chip-Tell),
  T90 Panel-Tell stabil (animiertes Glow-Pixel). Alle gemergt (fc1ef88), Suite 409 OK,
  gepusht. LIVE-BEFUND: classify-Schicht war nie gegen Tag-/aktuelle UI verifiziert;
  Abbruch-Kette der Laeufe: Intro -> Panel -> TagWelt -> Dream-Prep. OFFEN: T91
  Dream-Prep (Tap+classify, laeuft), Arena-Lobby ("did not open", 12:2x, unvermessen),
  danach naechster Gesamtlauf; +1-Charge/mem_probe warten weiter auf Gold.
- [2026-11-04 abend] Erkennungs-Haertung Runde 2 (T91-T99, alle gemergt bis T98=3eaba11, Suite 510):
  Dream-Prep-Fix, Arena-Lobby/Select, Victory-Overlay, Initial-Resilienz, Keyevent-Back-
  Fallbacks, Welt-HUD-Koordinaten, Hub-Klassifikation (T99 laeuft). LIVE heute: Dream-Fight
  gewonnen (T91), Arena-Fight gewonnen (Operator), AFK-Chest-Claim 2x verifiziert,
  Progress-Stage-Push kaempft auto (Stage 287!). BlueStacks-Input-Kollaps ~15:44 durch
  adb reboot + HD-Player-Neustart geheilt (Merke: keyevent geht immer, Maus-Klick als
  2. Pfad, Reboot heilt). OFFEN: T99 (Hub/Welt-Klassifikation), dann Lauf arena->dream (7/7),
  danach Night-Run 02:00.
