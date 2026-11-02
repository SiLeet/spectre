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
- Einschränkung (dokumentiert): HUD-Gegenprobe (Resonating Hall „Power 2xxK")
  wurde NICHT gezogen — PC in Benutzung (idle 0,05 s) + aktiver paralleler
  Writer zur Messzeit. Der gefundene Slot ist anker-verifiziert (exakter Wert =
  letzter verifizierter Memory-Wert, stabile Map-Entry-Struktur); ein falscher
  Kandidat mit exakt diesem Wert + Pointer-Struktur ist unwahrscheinlich.
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
- ⬜ T45j: Season-End-Arbitrage (≤6h: Chest/Attempts NICHT claimen; Tag 1: Push → Claim;
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
