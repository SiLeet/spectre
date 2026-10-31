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
- ⬜ **T18: v0.4.0-Release vorbereiten** — Version-Bump + CHANGELOG für
  hunt/hot/offsets/range-search (Tag wird von Hermes gesetzt). Brief in CLAUDE-TASKS.md.
- ⬜ **T19: Bot-Loop ehrt Task-Config** — schedule > interval > default pro Task,
  Task-Kopf-Bedingungen. Brief in CLAUDE-TASKS.md.
- ⬜ **T20: CLI-Referenz + README auf hunt/hot/offsets/range-search** aktualisieren.
  Brief in CLAUDE-TASKS.md.
- 📌 Hermes macht weiterhin den **Live-Teil** (hot am Gerät läuft seit b56f897;
  nächster Schritt: Gold-Offset-Bestätigung per Action-Diff).

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