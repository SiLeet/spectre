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

## P0 — Kern-Features (wahrscheinlich nächste Iteration)

### ⬜ T1: Web-Dashboard (`spectre serve`)
- **Berührt:** neues Crate `spectre-web/` (nur) + optional `spectre-cli` Subcommand `serve`
- **Ziel:** Live-Web-UI im Browser: Prozessliste, Memory-Regionen, Werte-Lese-Helper, Scan-Ergebnisse, Bot-Log.
- **Vorschlag:** Axum/Actix + minimales HTML/JS, `spectre serve --port 8787`.
- **DoD:** `spectre serve` startet, Browser zeigt Prozessliste + `read_u32`-Probe von einem PID; Tests für die HTTP-Handler; CI baut das neue Crate.

### ⬜ T2: Native Windows-Input-Simulation (`InputSimulator` Backend)
- **Berührt:** `spectre-bot/src/engine.rs` (oder neues Modul `spectre-bot/src/wininput.rs`), Testfile `spectre-bot/tests/wininput_test.rs`. KEINE anderen Crates.
- **Ziel:** `BotEngine` kann echte Klicks/Swipes auf native Windows-Fenster senden (SendInput/PostMessage) statt nur `adb shell input`.
- **DoD:** `InputSimulator` für Windows implementiert; CLI `--input-backend native_windows` akzeptiert es; Test, der den Treiber ohne echte Klicks validiert (Backend-Erkennung/Mocking); keine Änderung an anderen Crates.

### ⬜ T3: Offline-Dump-Diff (`spectre dumpdiff`)
- **Berührt:** `spectre-core` (neues Modul `diff.rs` + Tests) und `spectre-cli` (Subcommand `dumpdiff`, eigene Sektion im main.rs).
- **Ziel:** Zwei Raw-Dumps vergleichen → geänderte Bytes/Offsets ausgeben. So findet man Werte-Offsets, ohne live im Prozess zu suchen (Diff-Methode offline).
- **DoD:** `spectre dumpdiff a.dump b.dump --base 0x1000` zeigt geänderte Offsets mit Hex; 3+ Tests (gleich/anders/größenverschieden); kein Umbau bestehender APIs.

### ⬜ T4: Pointer-Chain-Discovery-Helfer (`spectre chain`)
- **Berührt:** `spectre-core` (neues Modul `chain.rs` + Tests), `spectre-cli` (Subcommand `chain`).
- **Ziel:** Nachdem `search` die echte Adresse gefunden hat, Pointer-Kette vom statischen Base zur Adresse auflösen/anzeigen — stabile Offsets über Game-Updates hinweg.
- **DoD:** `spectre chain <pid> <static_offset>` folgt Pointer u64-Ketten mit Offsets; Maximum-Tiefe; Test mit FakeReader-Daten; Dokus in `docs/game-integration.md`.

---

## P1 — Verbesserungen & Docs

### ⬜ T5: CLI-Referenz-Doku (auto-generiert)
- **Berührt:** `docs/cli-reference.md` (neu), evtl. `spectre-cli` help-Texte.
- **Ziel:** Vollständige, lebende CLI-Referenz für alle Subcommands + Flags.
- **DoD:** Jedes Subcommand mit Beispiel; `--help`-Ausgabe stimmt mit Doku überein (manueller Abgleich).

### ⬜ T6: Lua-API erweitern (read_fields + batch)
- **Berührt:** `spectre-lua/src/api.rs` (+ Tests im Crate).
- **Ziel:** `spectre.read_fields({pid, name=...})` Batch-Read; `spectre.regions(pid)` exportieren.
- **DoD:** Neue Lua-Funktionen dokumentiert in `spectre-lua/README.md`; Skript-Test in `examples/`.

### ⬜ T7: CRON-Like Scheduling im Bot
- **Berührt:** `spectre-bot/src/scheduler.rs` + `config.rs` (+ Tests).
- **Ziel:** README verspricht „interval scheduling"; optional `cron`-Ausdruck pro Task (simple 5-Feld-Cron oder Intervall nur erweitern? — erst Review).
- **DoD:** Task kann `schedule: "0 */6 * * *"` statt `interval_ms`; Unit-Tests für Cron-Parser; Docs-Update.

### ⬜ T8: Beispiel-Repository einrichten (Challenge-Repo)
- **Berührt:** `examples/` erweitern, `docs/` (nur).
- **Ziel:** Fertiges fertiges Beispiel: `examples/afk-bot-config.yaml` mit realistischen Offsets als „Challenge", Lua-Skript + Doku, damit jemand das Projekt in 10 Minuten ausprobieren kann.
- **DoD:** Ein Tutorial-Walkthrough in `docs/getting-started.md` von 0 auf laufenden Scan mit dem Challenge-Repo.

---

## P2 — Ausblick / ABER mit Achtung

### ⬜ T9: Web-Dashboard Auth + Produktions-Härtung
- **Berührt:** `spectre-web/` (eigenes Crate, in T1 angelegt).
- **DoD:** Nur-Lesen-Zugriff, CORS-Limits, keine Secrets; Security-Review.

### ⬜ T10: Multi-Instanz/Mehrere Emulatoren orchestrieren
- **Berührt:** `spectre-adb` (+ CLI).
- **DoD:** `adb list` parallel ansprechen, mehrere Targets in einem Bot-Lauf.

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