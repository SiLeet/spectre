# Claude Code — Task-Briefe für Spectre

> **Zweck:** Eigenständige, kopierfertige Prompts, die Claude Code im
> `C:\Users\Sigi\spectre`-Workspace abarbeiten kann. Jeder Task berührt
> **disjunkte Dateien** → parallele Ausführung ohne Merge-Konflikte.

---

## ⚙️ Gemeinsamer Kontext (in JEDEN Prompt einfügen)

```
WORKSPACE: C:\Users\Sigi\spectre  (Rust workspace, edition 2024, 8 Crates)
CRATES: spectre-core (types/traits/scanner), spectre-adb, spectre-native,
        spectre-game (YAML offsets), spectre-bot (engine), spectre-lua,
        spectre-cli, spectre (umbrella)

TOOLCHAIN (WICHTIG — auf diesem PC ist MSVC defekt):
  MSVC-Linker fehlt. IMMER die GNU-Toolchain verwenden:
  export PATH="$HOME/.cargo/bin:/c/Users/Sigi/AppData/Local/Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin:$PATH"
  cargo +stable-x86_64-pc-windows-gnu check/test/clippy ...
  (Niemals plain `cargo` — das nutzt die kaputte MSVC-Toolchain.)

DEFINITION OF DONE (IMMER):
  - cargo +stable-x86_64-pc-windows-gnu check --workspace   -> 0 errors
  - cargo +stable-x86_64-pc-windows-gnu test -p <dein-crate> -> alle grün
  - cargo +stable-x86_64-pc-windows-gnu clippy --workspace --all-targets -> 0 warnings
  - git add -A && git commit -m "<msg>" auf Branch feature/Tx-...
  - Dateien und geänderte Funktionen im Abschlussbericht auflisten

CODE-STIL:
  - echtes Rust 2024: `Ok(x)` statt `return x?;`, `as`-Casts statt `u32(x)`,
    keine Pseudo-Rust-Muster. anyhow::Result. tracing::info!/debug!.
  - Wenn ein Pfad-Feld geändert wird: `cargo fmt` danach laufen lassen.
```

---

## T2 — Native Windows-Input-Simulation (spectre-bot)

**Berührt:** `spectre-bot/src/engine.rs` (oder neues Modul `spectre-bot/src/wininput.rs`), Tests. **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

In spectre-bot existiert `pub trait InputSimulator: Send + Sync` mit 5 Methoden
(Default no-op, alle -> anyhow::Result<()>):
  click(x:u32, y:u32), tap_hold(x:u32,y:u32,millis:u64),
  swipe(x1,y1,x2,y2,millis:u64), scroll(delta:i32), key(key:&str)

AUFGABE: Implementiere ein Windows-InputSimulator-Backend:
  1. Neues Modul spectre-bot/src/wininput.rs mit struct WindowsInput.
  2. Implementiere InputSimulator für WindowsInput per RAW Win32 FFI:
     - click/tap:  mouse_event/SendInput (MOUSEEVENTF_LEFTDOWN|LEFTUP) auf
       Bildschirmkoordinaten (x,y)
     - swipe:   INPUT-Struktur mit MOUSEEVENTF_MOVE plus optional
       MOUSEEVENTF_LEFTDOWN/UP über mehrere Schritte (Duration -> move-split)
     - scroll:  MOUSEEVENTF_WHEEL mit delta
     - key:     KEYBDINPUT mit VK-Code (key als "A".."Z"/"0".."9"/"ENTER"/"ESC")
     - FFI nur kernel32/user32, ohne windows-rs-Crate! (unsafe extern "system")
  3. Re-export in spectre-bot/src/lib.rs:  pub use wininput::WindowsInput;
  4. cfg(windows)-Gate: auf Linux kompiliert das Modul NICHT (trait bleibt no-op).
  5. Tests (spectre-bot/tests/wininput_test.rs oder #[cfg(test)] im Modul):
     - WindowsInput::new() konstruierbar
     - backends sind Send+Sync
     - KEINE echten Klicks im Test! Stattdessen: ein Test, der ein
       RamInputSimulator-Mock definiert und prüft, dass BotEngine::run_action
       damit korrekt dispatched (click(x,y) kommt an).
  6. CLI braucht NIEMAND anzufassen (spectre-cli ruft "native_windows" noch
     nicht — nur das Crate). Wenn du Lust hast, darfst du in spectre-cli einen
     TODO-Kommentar an der create_input-STELLE ergänzen.

BRANCH: feature/T2-wininput
```

---

## T3 — Offline-Dump-Diff (`spectre dumpdiff`)

**Berührt:** `spectre-core/src/diff.rs` (neu) + Tests; `spectre-cli/src/main.rs` (Subcommand `dumpdiff`). **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

ZIEL: Zwei Raw-Dump-Dateien (wie von `spectre dump --format raw` erzeugt)
byteweise vergleichen und geänderte Offsets anzeigen — die "Diff-Methode"
der Offset-Discovery offline.

SCHRITTE:
  A) spectre-core/src/diff.rs (neu):
     pub struct DumpDiff { pub changed: Vec<ChangedRegion> }
     pub struct ChangedRegion { pub offset: usize, pub old_bytes: Vec<u8>,
                                pub new_bytes: Vec<u8> }
     pub fn diff_dumps(old: &[u8], new: &[u8]) -> DumpDiff
     - Gleiche Länge: Vergleiche byteweise, fasse benachbarte Änderungen zu
       Regionen zusammen (max gap 16 Bytes).
     - Unterschiedliche Länge: behandle das Differenz-Ende als eine Region.
     - Methoden: DumpDiff::changed_count(), DumpDiff::regions()
     - Tests in spectre-core/tests/diff_test.rs:
       * identische Dumps -> 0 Regionen
       * eine Byte-Änderung -> 1 Region, offset korrekt
       * mehrere benachbarte Bytes -> 1 Region
       * zwei weit getrennte Änderungen -> 2 Regionen
       * unterschiedliche Längen -> letzte Region deckt Differenz-Ende
  B) spectre-cli/src/main.rs: füge Subcommand `dumpdiff` hinzu:
     structopt: struct DumpDiffArgs { old: String (positional), new: String
                (positional), #[structopt(long="base", default_value="0")]
                base: String, #[structopt(long="json")] json: bool }
     - parse base via parse_u64 (existiert)
     - Lade beide Dateien, rufe diff_dumps auf
     - Ausgabe (nicht-json): pro Region: "0x{:X}  old: <hex>  new: <hex>"
     - json: serde_json::to_string_pretty
     - Dispatch in main(): Some(SubCommand::DumpDiff(cmd)) => run_dumpdiff(cmd)
     - Unit-Tests im #[cfg(test)] mod der CLI für den Hex-Formatter
  C) Doku-Zeile oben im main.rs-Doc-Header ergänzen (dumpdiff usage).
  D) cargo fmt laufen lassen.

BRANCH: feature/T3-dumpdiff
```

---

## T5 — CLI-Referenz-Dokumentation

**Berührt:** NUR `docs/cli-reference.md` (neu). **KEINE** Crate-Dateien.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

Erstelle docs/cli-reference.md als vollständige, akkurate Referenz der
CLI. Führe dazu aus:
  cd /c/Users/Sigi/spectre
  export PATH="$HOME/.cargo/bin:/c/Users/Sigi/AppData/Local/Microsoft/WinGet/Packages/BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe/mingw64/bin:$PATH"
  cargo +stable-x86_64-pc-windows-gnu build -p spectre-cli 2>/dev/null
  ./target/debug/spectre.exe --help
  ./target/debug/spectre.exe <subcommand> --help   (für JEDES Subcommand)

Doku-Struktur:
  - Übersicht + globale Flags
  - Pro Subcommand: Beschreibung, Syntax, alle Flags, 1-2 Praxisbeispiele
  - Subcommands: scan, dump, find, regions, search, bot, script, info, adb
  - Abschnitt "Offline-Workflow": dump -> scan --dump
  - Abschnitt "Offset-Discovery": search + --continue Workflow
  - Abschnitt "Bot": Verweis auf examples/bot-config.yaml + YAML-Tag-Syntax
    (!MemoryCheck, !U64 ...)
  - Markdown-Tabellen für Flags. Genaue Ausgabe der --help-Texte übernehmen.

Vor dem Commit: prüfen, dass `--help`-Ausgaben mit der Doku übereinstimmen
(Abgleich manuell). Keine Crate-Datei ändern!

BRANCH: feature/T5-cli-docs
```

---

## T6 — Lua-API erweitern (Batch-Read + regions)

**Berührt:** `spectre-lua/src/api.rs`, `spectre-lua/README.md`, ggf. `examples/`. **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

ZIEL: Die Lua-Sandbox bekommt zwei neue Funktionen im `spectre`-Modul.

BESTEHENDE API (in api.rs): read_u32, read_u64, read_i32, read_f32,
read_string(pid,addr,len), find_process(name)->pid|nil,
scan(pattern_table)->{name->[addrs]}.
context() liefert mlua::AppDataRef<LuaContext> mit {reader, bot}.

AUFGABE:
  1. spectre.read_fields(pid, fields_table) -> result_table
     - fields_table: { {name="hp", addr=0x..., type="u32"|"f32"|"u64"|"string", len=32}, ... }
     - Ergebnis: { name -> number|string } (oder nil wenn Read fehlschlägt)
     - Implementiere Batch-Read (loop über Einträge, kein Lua-Callback nötig)
  2. spectre.regions(pid) -> result_table
     - Liefert eine Lua-Tabelle { start=..., end=..., perms="rw-", size=... }
       für jede MemoryRegion (reader.memory_regions(pid))
  3. Binde beide in register() des spectre-Moduls ein (mlua register_function/
     create_function Muster folgen).
  4. Dokumentiere beide in spectre-lua/README.md (Signatur + Beispiel-Lua).
  5. Tests: Du darfst ein kleines Rust-Integrationstest-File
     spectre-lua/tests/sandbox_test.rs anlegen, das LuaSandbox mit einem
     Fake-MemoryReader (in-memory buffer, wie in spectre-core/tests) nutzt:
     read_u32 + read_fields + regions asserten.
     (FakeReader: implementiere spectre_core::MemoryReader manuell — siehe
     spectre-core/tests/scanner_test.rs für ein Beispiel.)

BRANCH: feature/T6-lua-api
```

---

## T7 — Cron-Like Scheduling im Bot

**Berührt:** `spectre-bot/src/scheduler.rs`, `spectre-bot/src/config.rs`, Tests.
**KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

ZIEL: Bot-Tasks können optional per Cron-ähnlichem Ausdruck statt fixem
interval_ms laufen.

BESTEHENDES MODELL:
  - BotTask { name, actions, interval_ms: u32, enabled: bool, conditions }
  - TaskScheduler mit tick = GCD aller Intervalle, `start(Arc<BotEngine>)`.

AUFGABE:
  1. Neues Modul spectre-bot/src/cron.rs:
     pub struct CronSchedule { pub minute: Option<u32>, pub hour: Option<u32>,
                               pub day: Option<u32>, pub month: Option<u32>,
                               pub weekday: Option<u32> }
     pub fn parse_cron(expr: &str) -> anyhow::Result<CronSchedule>
     - 5 Felder: minute hour day month weekday
     - Unterstütze: "*" (Any -> None), "5" (exakt), "*/15" (step),
       "1,2,3" (Liste -> nimm erstes Element als Option, dokumentiere Limit)
     - Bei ungültigem Ausdruck: anyhow!-Fehler
     pub fn matches(schedule:&CronSchedule, now: chrono::DateTime<Local>)
        -> bool  (wenn Feld None -> immer true)
  2. BotTask erweitern: #[serde(default, skip_serializing_if="Option::is_none")]
     pub schedule: Option<String>  (neben interval_ms, beides parallel ok)
     - ohne chrono-Crate: nutze std::time::SystemTime + manuelles
       (year/month/day/hour/min/weekday) Umrechnen, ODER füge chrono als
       Dependency hinzu — entscheide selbst (chrono bevorzugt).
  3. TaskScheduler: Wenn Task.schedule Some(expr) ist, berechne pro Tick,
     ob matches() true -> Aktionen feuern; interval_ms bleibt der Tick-Raster.
  4. Unit-Tests in spectre-bot: parse_cron valid/invalid, matches für
     "*/15 * * * *" (Minute step), "0 */6 * * *" (Stunde step).
  5. Beispiel in examples/bot-config.yaml: ein Task mit schedule statt
     interval_ms (Doku-Kommentar).

BRANCH: feature/T7-cron
```

---

## T10 — Multi-Emulator Orchestrierung (spectre-adb)

**Berührt:** `spectre-adb/src/reader.rs`, Tests. **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

ZIEL: AdbReader kann mehrere verbundene ADB-Geräte parallel ansprechen.

BESTEHEND: AdbReader { host, port, serial: Option<String> } mit
`adb connect <host>:<port>` + fallback `adb -s <serial> shell ...`.
run_adb_shell baut den Befehl pro Aufruf.

AUFGABE:
  1. Neues Modul spectre-adb/src/multi.rs:
     pub struct AdbManager { pub readers: Vec<AdbReader> }
     pub fn discover() -> anyhow::Result<Vec<AdbReader>>
     - Ruft `adb devices` auf, parst die Device-Liste (Zeilen: <serial>\t<state>)
     - Für jedes device im state "device": AdbReader { serial: Some(serial),
       host: "localhost", port: 5555 } (Bluestacks/KO: serial erkennbar)
     - Filtert "unauthorized"/"offline" mit tracing::warn
  2. pub fn find_process_on_all(&self, name:&str)
     -> Vec<(u32 /*pid*/, String /*serial*/)>  — iteriert Readers, sammelt
     Treffer; Fehler einzelner Reader werden gewarnt und übersprungen.
  3. Re-export in spectre-adb/src/lib.rs.
  4. Tests: parse-Funktion für adb devices-Output kapseln und testen:
     fn parse_adb_devices(output:&str) -> Vec<(String,String/*serial,state*/)>
     - mit Beispiel-Output (2 devices + 1 unauthorized)
  5. KEINE CLI-Änderungen (CLI nutzt noch single reader; TODO-Kommentar dort
     ist optional).

BRANCH: feature/T10-multi-adb
```

---

## Status

- ✅ Erledigt & gemergt: T2 (WinInput), T3 (DumpDiff), T5 (Docs), T6 (Lua-API),
  T7 (Cron), T10 (Multi-ADB), T1 (Web-Dashboard), T9 (Web-Härtung),
  T4 (Chain-CLI), T8 (Challenge-Repo) + Release v0.2.0/v0.3.0.
- ✅ Live-ADB-Fixes (2026-10-31): Root-Fallback, Android-ps-Parser, Serial-Pinning,
  page-aware 4K-Reads (`6a36d58`), `spectre hunt` (`3e742dd`), Game-Guides (`b330dd8`).
- ⬜ **Neu (Claude-ready, alle OHNE Live-Emulator):**
  - T13 (On-device hot-scan) — Code + Unit-Tests; Live-Verifikation macht Hermes
  - T14 (search --min/--max Range-Suche) — direkt nützlich für gerundete Anzeigen
  - T15 (offsets introspect + Validator) — Selbst-Hilfe für die Offsets-YAML
  - T16 (AFK-Beispiel-Bots safe actions) — nur examples/docs
  - T17 (Native Linux-Reader paritätisch) — eigenständig, nur linux.rs
- Hermes arbeitet parallel an der Live-Offset-Bestätigung (T11) — braucht den
  laufenden Emulator, das kann Claude NICHT abnehmen.

## Empfehlung: Start-Reihenfolge (Phase 2)

| # | Task | Schwierigkeit | Warum zuerst |
|---|------|--------------|--------------|
| 1 | **T4 Chain-CLI** | Leicht-Mittel | eigenständig, klein, sofort testbar |
| 2 | **T1 Web-Dashboard** | Mittel-Groß | großes Sichtbarkeits-Feature, eigenes Crate |
| 3 | **T8 Challenge-Repo** | Leicht | reine Docs/Examples, parallel zu allem |
| 4 | **T9 Web-Härtung** | Mittel | MUSS nach T1 kommen (T1 ist Voraussetzung) |

**Hinweis:** T4, T8 können sofort parallel laufen. T1 sollte vor T9
bearbeitet werden (T9 hängt davon ab). Ein Task = ein Branch
(feature/Tx-...) + ein Commit-Vorschlag pro logischem Schritt.

---

## T1 — Web-Dashboard (`spectre serve`)

**Berührt:** neues Crate `spectre-web/` (komplett neu), `spectre-cli/src/main.rs` (Subcommand `serve`), Workspace-Root `Cargo.toml` (member hinzufügen). **KEINE** Änderungen an bestehenden Crate-Logiken (nur neue Dateien + CLI-Dispatch).

```
KONTEXT-Teil (oben) + folgende Aufgabe:

ZIEL: Ein Web-Dashboard, das spectre-Fähigkeiten im Browser zeigt.

HINTERGRUND (existierende APIs):
  - spectre_core::MemoryReader trait mit: find_process(&str) -> Vec<ProcessInfo>,
    list_processes(), memory_regions(pid) -> Vec<MemoryRegion{start,end,perms,path}>,
    read_bytes(pid,addr,size), read_u32/read_f32/read_string, scan(...)
  - spectre_native::create_default_reader() -> Box<dyn MemoryReader>
  - ProcessInfo { pid: u32, name: String }; MemoryRegion { start: u64, end: u64,
    perms: String, path: Option<String> }
  - scan: spectre_core::scan_memory(reader, pid, patterns, config) sowie
    spectre_core::ScanPattern/PatternField/ScanValue/ValueType

AUFGABE:
  1. Neues Crate spectre-web:
     - Cargo.toml: name spectre-web, deps: spectre-core (workspace),
       axum (^0.7 oder aktuell), tokio (workspace), anyhow, tracing, serde,
       serde_json. KEIN spectre-native-Dependency direkt — der/die Reader
       werden per Trait-Objekt injiziert.
     - src/lib.rs: pub struct DashboardApp { reader: Arc<dyn MemoryReader> }
       mit pub fn new(reader: Arc<dyn MemoryReader>) -> Self
     - src/routes.rs: axum-Router mit Endpunkten:
         GET  /                     -> einfaches HTML (eingebettet)
         GET  /api/processes        -> all processes (JSON)
         GET  /api/regions?pid=N    -> memory regions (JSON)
         GET  /api/read?pid=N&addr=0x...&type=u32|f32|string&size=64 -> Wert (JSON)
         GET  /api/search?pid=N&type=u32&value=42  -> Adressen (JSON)
       - Response-Struktur konsistent: { "ok": true, "data": ... } oder
         { "ok": false, "error": "..." }
     - src/lib.rs: pub async fn serve(self, port: u16) -> anyhow::Result<()>
       (bindet 127.0.0.1:port, startet axum::serve)
  2. CLI: spectre-cli/src/main.rs erweitern:
     - Subcommand: #[structopt(about="Start the web dashboard")] Serve(ServeArgs)
     - ServeArgs { port: u16 (default 8787) }
     - run_serve: create_default_reader() -> DashboardApp::new(...).serve(port)
     - Dispatch im main()-match + Doc-Header oben ergänzen
  3. Workspace-Root Cargo.toml: "spectre-web" in members + workspace.dependencies
     (falls nötig axum dort statt im Crate definieren)
  4. Tests: spectre-web/tests/dashboard_test.rs — nutzt tokio::test mit einem
     FakeReader (in-memory, wie spectre-core/tests/scanner_test.rs: regions +
     kleine Bytes). Starte DashboardApp::serve auf Port 0 (oder Test-Port),
     httptest-Requests über reqwest ODER axum::test::oneshot (aktuellstes)
     auf /api/processes und /api/read — prüfe JSON-Shape.
  5. cargo fmt + cargo clippy laufen lassen.

WICHTIG: Das Crate muss auf Linux UND Windows kompilieren (kein CFG-auf
Windows-only-Logik in spectre-web selbst; die Reader-Erzeugung bleibt im CLI).

BRANCH: feature/T1-web-dashboard
```

---

## T4 — Pointer-Chain-CLI (`spectre chain`)

**Berührt:** `spectre-core/src/chain.rs` (neu) + Tests, `spectre-cli/src/main.rs` (Subcommand `chain`). **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND (bereits vorhanden):
  - MemoryReader::resolve_ptr_chain existeirt bereits im Trait:
    fn resolve_ptr_chain(&self, pid, base: u64, offsets: &[u64], little: bool)
    -> anyhow::Result<Option<u64>>   (folgt u64-Pointer-Kette)
  - parse_u64(s) existiert in spectre-cli (dezimal oder 0x-hex)
  - create_reader(adb, host, port) -> Box<dyn MemoryReader> existiert
  - resolve_pid(reader, name, hint) existiert

AUFGABE:
  1. spectre-core/src/chain.rs (neu):
     pub struct PointerChain { pub base: u64, pub offsets: Vec<u64>,
                               pub resolved: Option<u64> }
     - Nützliche Helfer: pub fn follow(reader:&dyn MemoryReader, pid:u32,
       base:u64, offsets:&[u64], little:bool) -> anyhow::Result<PointerChain>,
       resolved = resolve_ptr_chain(...)
     - pub fn follow_until_end(reader, pid, start:u64, max_depth:u32,
       little:bool) -> anyhow::Result<PointerChain> — liest u64 am start,
       springt zu diesem Pointer, wiederholt bis max_depth oder 0/NULL.
       Sammelt dabei alle Zwischen-Offsets.
     - Tests in spectre-core/tests/chain_test.rs mit FakeReader:
       * follow mit 2 Offsets -> korrekter Endwert
       * follow_until_end bricht bei NULL ab
       * follow_until_end respektiert max_depth
  2. CLI-Subcommand `chain`:
     struct ChainArgs { pid: Option<u32> (optional, auto-detect über name),
                        address: String (positional, dezimal/0x),
                        #[structopt(long="depth", default_value="16")] depth: u32,
                        #[structopt(long="little")] little: bool (default true),
                        #[structopt(long="adb")] adb: bool }
     - run_chain: reader -> follow_until_end(pid, addr, depth, little)
       -> druckt jede Stufe: "addr: 0x... -> *0x... = 0x..." und final
       resolved Adresse. JSON via --json.
     - Dispatch + Doc-Header.
  3. cargo fmt.

BRANCH: feature/T4-chain
```

---

## T8 — Challenge-Repo / Quickstart-Beispiel

**Berührt:** NUR `examples/`, `docs/getting-started.md`, evtl. `README.md`. **KEINE** Crate-Dateien.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

ZIEL: Jemand soll das Projekt in ~10 Minuten von 0 auf einen laufenden
Scan bringen („Challenge-Repo"-Erlebnis).

VORHANDEN: examples/afk-bot.lua, examples/bot-config.yaml,
games/afk-journey/offsets.yaml (Platzhalter-Offsets), docs/getting-started.md.

AUFGABE:
  1. examples/README.md (neu) — „10-Minuten-Quickstart":
     - Schritt 0: cargo build + Binary installieren (GNU-Toolchain-Hinweis
       für Windows, siehe Kopf)
     - Schritt 1: Probe ausprobieren ohne echtes Spiel: wie man mit
       `spectre dump`/`search` auf einem eigenen Prozess Werte findet
       (z.B. Öffne einen Prozess, suche 42 — allgemein halten)
     - Schritt 2: AFK-Journey-Beispiel: `spectre find`, `spectre search`
       Workflow, `spectre scan --dump` mit einer selbst erzeugten Dump-Datei
     - Schritt 3: Bot: `spectre bot examples/bot-config.yaml --dry-run`
     - Schritt 4: Lua: `spectre script examples/afk-bot.lua`
  2. examples/bot-config.yaml ergänzen: 1 Task mit `schedule:` (cron)
     statt nur interval_ms (Doku, dass T7 das unterstützt).
  3. docs/getting-started.md: oben einen „TL;DR"-Block (3 Zeilen: build,
     find, search) + Link auf examples/README.md.
  4. Prüfen: alle im Quickstart genannten Befehle existieren wirklich —
     nötigenfalls `--help` jedes Subcommands checken.

BRANCH: feature/T8-challenge
```

---

## T9 — Web-Dashboard-Härtung (nach T1)

**Berührt:** `spectre-web/` (wird in T1 angelegt). **Setzt T1 voraus** — erst nach T1 mergen!

```
KONTEXT-Teil (oben) + folgende Aufgabe:

ZIEL: Das Dashboard sicherer machen, bevor es jemand öffentlich exposed.

VORAUSSETZUNG: Task T1 (spectre-web) ist gemergt. Dieser Brief nur danach.

AUFGABE:
  1. Read-only-Prinzip fixieren:
     - KEINE write/execute-Endpunkte (Bots starten, Werte schreiben) —
       falls T1 versehentlich welche hat: entfernen.
     - CORS: keine wildcard-Zugriffe; Origin-Whitelist (leer = nur localhost)
  2. Rate-Limiting: einfacher In-Memory-Limiter pro IP für /api/read und
     /api/search (z.B. max 60 req/min), mit tracing::warn bei Überschreitung.
  3. Keine Secrets/Pfade leaken: Fehler-Antworten enthalten KEINE
     absoluten Pfade, keine Umgebungsvariablen. (Nur "read failed".)
  4. CLI: `serve` bindet standardmäßig 127.0.0.1. Falls ein
     --host-Flag existiert: bei 0.0.0.0 Warnung + Bestätigung nötig — sonst
     gar kein --host-Flag anbieten.
  5. Tests: Rate-Limiter-Einheit (N erlaubt, N+1 blockiert), CORS-Header
     Test, Fehler-Antwort-Shape ohne Pfad-Leak.
  6. cargo fmt + clippy.

BRANCH: feature/T9-web-hardening
```

---

## T13 — On-device hot-scan (`spectre hot`) für kürzere Diff-Zyklen

**Berührt:** `spectre-adb/src/reader.rs` (neue Methode), `spectre-adb/src/lib.rs`, `spectre-cli/src/main.rs` (Subcommand `hot` + hunt erweitern optional). **KEINE** Änderung an spectre-core.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND (aus Live-Session 2026-10-31, AFK Journey auf BlueStacks):
  - Offset-Discovery braucht VORHER/NACHHER-Dumps um kurze Abstände (Sekunden),
    sonst ist der Diff mit Animations-Churn verrauscht (1h-Abstand = 244k Slots).
  - toybox-dd auf Android kann kein iflag=skip_bytes,count_bytes; read_bytes
    splittet bereits: Kopf/Tail bs=1, alignierter Mittelteil bs=4096 (~3.3 MB/s).
  - Der Flaschenhals ist HEX-TEXT über die adb-Pipe, nicht dd.

AUFGABE:
  1. Neue Methode in spectre-adb/src/reader.rs (impl AdbReader):
     pub fn grep_memory(&self, pid: u32, patterns: &[Vec<u8>], chunk: u32)
       -> anyhow::Result<Vec<(u64 /*abs addr*/, usize /*pattern idx*/)>>
     - Führt pro 4K-aligned Chunk (default 1 MiB) auf dem GERÄT aus:
         su -c 'dd if=/proc/<pid>/mem bs=4096 skip=<n> count=<k> 2>/dev/null
                | grep -aboF -e <pat1> -e <pat2> ...'
       Hinweis: grep -abo liefert `offset:match` Zeilen; offset ist relativ zum
       Chunk-Start. -F = literale Bytes (Patterns als Binär?). Wenn Binär-Patterns
       mit GREP nicht gehen (NUL-Bytes), nutze stattdessen xxd -p auf dem Gerät
       und grep nach den HEX-Strings:
         ... | xxd -p -c <n> | grep -nF <hexpattern>
       und rechne Zeilennummer * Spaltenbreite zurück. Implementiere die
       xxd-Variante zuerst (robuster), dokumentiere die Wahl im Code.
     - Geänderter Bereich: nur für AdbReader; native bleibt unverändert.
  2. CLI-Subcommand `spectre hot <pid> <hex> [--adb] [--base 0] [--limit N] [--json]`:
     - Search across all readable anonymous rw regions for the byte pattern,
       printing absolute addresses; only matches cross the wire.
     - Dispatch in main() + Doc-Header.
  3. Unit-Tests (spectre-adb/src/reader.rs #[cfg(test)]):
     - hex -> xxd-line -> offset Rückrechnung
     - grep-Ausgabe-Parser (offset:match) für ein Beispiel
  4. cargo fmt + clippy. KEINE spectre-core-Änderungen.

BRANCH: feature/T13-hot-scan
```


---

## T14 — `spectre search` Range-Suche (`--min/--max`)

**Berührt:** `spectre-cli/src/main.rs` (SearchArgs + run_search), Tests. **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND: Aktuell sucht `spectre search <pid> <type> <value>` nur EXAKTE
Werte. In der Praxis kennt man den Zielwert oft nur gerundet (Spiel zeigt
"259K", echter Wert 259850). Eine Range-Suche wäre der Unterschied zwischen
"funktioniert" und "frustrierend".

AUFGABE:
  1. SearchArgs erweitern: #[structopt(long="min")] min: Option<String> und
     #[structopt(long="max")] max: Option<String>. value bleibt optional,
     wenn min+max gesetzt sind (required_unless für value anpassen: value
     ODER (min UND max)).
  2. parse_search_value erweitern: wenn min/max gesetzt, statt exaktem Bytes
     einen Mini-Range-Vergleich erlauben. Pragmatisch: In run_search bei
     range-Modus für JEDE Kandidatenadresse read_value machen und prüfen,
     ob der numeric value in [min..max] liegt (nicht byte-vergleich).
     - Für u8/u16/u32/u64/i8/.../f32/f64: numerischer Vergleich über die
       passende read_* -Methode des Readers.
     - Für string: nicht unterstützt (Fehler, wenn type=string mit min/max).
  3. Im Range-Modus: scan über alle Regions (wie bisher), aber statt
     Byte-Vergleich der Bufs den numerischen Check pro Fund nutzen. Du darfst
     scan_memory mit exakten Werten NICHT pro Range-Wert aufrufen (zu langsam);
     nutze stattdessen einen einfachen Byte-Scan nach fixen Bytes VOR dem
     numerischen Check? NEIN — einfacher und korrekt: Im Range-Modus liest du
     Region für Region via reader.read_bytes (gleiche Logik wie Scanner),
     packst pro width-aligned Slot den Wert und filterst numerisch. Das
     Ergebnis ist eine Adressliste wie bisher.
  4. --continue-Modus: gleiche Filterung auf den vorherigen Address-Set.
  5. Tests (spectre-cli #[cfg(test)] oder spectre-core/tests):
     - parse_search_value mit min/max
     - Range-Ergebnis-Filter (kleiner FakeReader der 259000-259999 liefert)
  6. Doku: Doc-Header oben in main.rs + docs/cli-reference.md Abschnitt search
     um --min/--max ergänzen.

BRANCH: feature/T14-search-range
```


---

## T15 — `spectre offsets` introspect + Validator

**Berührt:** `spectre-cli/src/main.rs` (Subcommand `offsets`), `spectre-game/src/*.rs` (falls Validator dort sinnvoller). **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND: Die Offsets-YAML (games/<game>/offsets.yaml) sind die zentrale
Spielwissen-Datei. Es gibt kein CLI-Kommando, um sie einfach ANZUSEHEN oder
zu validieren (falsche Feld-Typen, fehlende Strukturen, doppelte Offsets).

AUFGABE:
  1. Neues Subcommand `spectre offsets [game]`:
     - Ohne Argument: listet verfügbare Games (games/*/offsets.yaml)
     - Mit game: lädt die YAML über spectre_game::load (bestehende API),
       zeigt Strukturen + Felder als Tabelle: Struktur | Feld | Typ | Offset
       | Beschreibung. --json für Maschinenausgabe.
  2. Validierung beim Laden ODER als --validate-Flag:
     - Alle Strukturnamen einzigartig
     - Keine doppelten Feldnamen pro Struktur
     - Keine überlappenden Feld-Bereiche innerhalb einer Struktur
       (start = offset, end = offset + size(type); Warnung bei Überlapp,
       Error erst ab Konfig-Detail -> Warnung ausgeben)
     - Game-Version vorhanden und nicht leer
     - Report: "ok" oder Liste der Probleme (mit Struktur/Feld-Namen)
  3. Tea hinzufügen in der CLI: Dispatch + Doc-Header.
  4. Tests (spectre-game/tests/loader_test.rs erweitern ODER neue Tests in
     spectre-cli): Validator findet
     - doppelte Struktur
     - überlappende Felder
     - leere Version
  5. Alle games/offsets.yaml müssen danach die Validierung bestehen (falls
     afk-journey Platzhalter-Offsets überlappen, hier NICHT faken — Offsets
     selbst bleiben, nur Debug-Output).

BRANCH: feature/T15-offsets-validate
```


---

## T16 — Bot-Beispiel mit echten Safe-Aktionen (AFK Journey)

**Berührt:** `examples/` (neue Dateien), `docs/` (kurze Ergänzung). **KEINE** Crate-Dateien.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND (aus docs/afk-journey-guide.md): Es gibt sichere Trigger-Aktionen
im Spiel (Claim Daily/Login-Rewards, Homestead-Requests, AFK-Idle-Truhe), die
Währungen ändern ohne Risiko. Die Beispiel-Bots (examples/bot-config.yaml,
examples/afk-bot.lua) sollen diese Muster zeigen — OHNE echte Offsets zu
brauchen (Platzhalter sind ok, aber bitte als solche markiert).

AUFGABE:
  1. examples/bot-config-afk.yaml (neu): Ein YAML-Bot-Config mit 3 Tasks:
     a) "claim_rewards": MemoryCheck auf einen Platzhalter-Gold-Offset
        (0xDEADBEEF) mit Kommentar "REPLACE with verified gold address",
        wenn > 0 -> Click auf Login-Rewards-Button (Koordinaten aus dem
        Guide als Kommentar)
     b) "idle_check": alle 5 Minuten Gold/EXP-Offsets lesen (Platzhalter),
        Log-Ausgabe
     c) "homestead_request": Beispiel mit Tap-Action (Koordinate kommentiert)
     - Nutze die echte YAML-Syntax (siehe examples/bot-config.yaml: !MemoryCheck,
       !U64,conditions, actions) — NICHT erfinden, erst die bestehende Datei
       lesen und das Schema übernehmen!
  2. examples/afk-bot.lua: erweitern um einen zweiten Bot-Modus "safe_claim"
     mit Kommentaren, wo echte Offsets eingesetzt werden. Leserichtig:
     bestehende APIs nutzen (spectre.find_process, read_u32 etc.).
  3. Neuer Abschnitt in examples/README.md: "AFK Journey Telegramm"-Muster —
     Schritt-für-Schritt, wie man aus einem Platzhalter-Offset einen echten
     macht (hunt -> dumpdiff -> offsets.yaml). Verweise auf
     docs/afk-journey-guide.md.
  4. NUR Doku/Beispiele — kein Crate-Code. Alle YAML/Lua mit --dry-run
     bzw. Syntax prüfen, wo möglich.

BRANCH: feature/T16-afk-examples
```


---

## T17 — Native Linux-Reader: `/proc/<pid>/mem` Support + Tests

**Berührt:** `spectre-native/src/linux.rs`, Tests (`spectre-native/tests/`). **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND: spectre-native hat einen Windows-Reader (windows.rs, live
verifiziert) und eine linux.rs-Datei. Der Linux-Reader soll paritätisch sein:
Prozessliste via /proc, Regions via /proc/<pid>/maps, Bytes via
open("/proc/<pid>/mem") + pread (nicht dd!). Auf Linux braucht man CAP_SYS_PTRACE
oder root für fremde Prozesse — eigener Prozess geht immer.

AUFGABE:
  1. linux.rs prüfen: Was existiert bereits (implementiert? TODO? nur Stubs)?
     Ergänze fehlende MemoryReader-Implementierungen:
     - list_processes: /proc scan für numerische Dirs + /proc/<pid>/comm
     - find_process: Substring über Namen (case-insensitive wie Windows)
     - memory_regions: /proc/<pid>/maps parsen (gleiche Struktur wie ADB-Parser,
       exists schon in spectre-adb — dort NACHBAUEN hier, nicht importieren)
     - read_bytes: open + libc::pread auf /proc/<pid>/mem; bei EPERM/EACCES
       sauberer Fehler "permission denied (need root or ptrace)"
     - process_name: comm lesen
     - backend_kind: NativeLinux
  2. Integrationstest (nur auf Linux, #[cfg(target_os="linux")]):
     - Spawn einen Probe-Binary (wie spectre-native/src/bin/probe.rs, das
       existiert bereits) ODER den eigenen Testprozess:
       * regions enthält mindestens eine rw-Region
       * read_bytes auf eine eigene Stack-Variable funktioniert
       * find_process("spectre") findet den Testprozess
     - Achtung: CI läuft auf windows+linux; Tests müssen auf beiden grün sein
       (cfg-Gates!).
  3. Kein Windows-Code anfassen. cargo fmt + clippy.

BRANCH: feature/T17-linux-reader
```

---
---

## T18 — Release-Pipeline für v0.4.0 vorbereiten (hunt/hot/offsets/range-search)

**Berührt:** `Cargo.toml` + `spectre-*/Cargo.toml` (Version-Bump), `CHANGELOG.md` (neu anlegen),
`.github/workflows/ci.yml`/`release.yml` NUR falls nötig. **KEINE** Crate-Quellcode-Änderungen.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND: main enthält inzwischen CLI-Features, die noch in KEINEM Release
sind: `spectre hunt` (Commit 3e742dd), `spectre hot` (T13 + Fix b56f897),
`spectre offsets` (T15), `spectre search --min/--max` (T14). Letztes Release
ist v0.3.0 und hat davon nichts. Der Release-Workflow (.github/workflows/
release.yml) baut bereits per Tag v* — vorbereiten muss man nur Versionen,
Changelog und den Tag-Commit.

AUFGABE:
  1. Version-Bump 0.3.0 -> 0.4.0 in ALLEN Cargo.toml (Workspace-Root + alle
     Crates; Achtung: workspace.dependencies vs. eigene Version-Felder
     prüfen, keine Abhängigkeits-Versionsangaben zwischen Crates brechen).
  2. CHANGELOG.md im Repo-Root neu anlegen mit Abschnitt "0.4.0 (2026-11-01)"
     und den Features seit 0.3.0, belegt durch die Commits (git log):
     - spectre hunt (CLI, Diff-basierte Offset-Kandidaten)
     - spectre hot (On-Device-Scan, xxd/od+grep, nur Treffer über adb)
     - spectre offsets (YAML-Viewer + Validator)
     - spectre search --min/--max (Range-Suche, auch f32)
     - spectre adb list/ping (Bluestacks-Discovery)
  3. KEIN Tag pushen! Nur den Vorbereitungs-Commit auf Branch
     feature/T18-release-v040. Der Tag v0.4.0 wird anschließend von einem
     Menschen/Hermes gesetzt, damit CI einmal sauber durchläuft.
  4. DoD: cargo check/test/clippy grün, CHANGELOG verlinkt Feature-Namen,
     keine Quellcode-Änderungen.

BRANCH: feature/T18-release-v040
```


## T19 — Bot-Loop: Intervall/Bedingungen/Zeitplan pro Task respektieren

**Berührt:** `spectre-bot/src/engine.rs`, `spectre-bot/src/scheduler.rs`, config-Deserialisierung, Tests. **KEINE** anderen Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND (bekannte Grenze, offen kommuniziert in examples/):
Die Bot-Engine führt Tasks aus, ignoriert aber pro Task-Konfiguration:
  - interval (wie oft der Task in der Schleife laufen darf)
  - Bedingungen am Task-Kopf (conditions) — nur Bedingungen IN Aktionen
    werden ausgewertet
  - schedule (cron) — existiert im Scheduler, wird aber von der Loop
    nicht konsistent mit interval abgestimmt
Ziel: Die Loop soll eine TaskConfig korrekt respektieren:
  a) schedule gesetzt -> Task nur zu den Cron-Zeiten starten
  b) sonst interval gesetzt -> Task höchstens alle N Sekunden starten
  c) sonst -> bei jeder Loop-Iteration (wie bisher)
Bedingungen am Task-Kopf sollen vor dem ersten Start ausgewertet werden
(field via ConditionSource, siehe engine.rs handle_condition) und die
Task-Ausführung überspringen, solange sie false sind.

AUFGABE:
  1. Lies spectre-bot/src/engine.rs + scheduler.rs und die TaskConfig-
     Struktur (wo auch immer definiert, vermutlich spectre-core oder
     spectre-bot/config.rs). Dokumentiere die IST-Semantik in einem
     Kommentar.
  2. Implementiere: Task-Loop ehrt schedule > interval > default.
     - Cron-Parsing existiert bereits (chrono, T7) — wiederverwenden.
     - Intervall-Tracking pro Task-Instanz (letzter Start-Zeitstempel),
       nicht global.
     - Wenn ein Task wegen schedule/interval/Bedingung übersprungen
       wird: debug!-Log-Eintrag mit Grund.
  3. Tests (mindestens):
     - Task mit interval: läuft nicht zweimal innerhalb des Intervalls
     - Task mit schedule: startet nur zum Cron-Zeitfenster (Test mit
       injizierter Zeitquelle, nicht echten Sleep)
     - Task-Kopf-Bedingung false -> Task wird übersprungen, andere Tasks
       laufen trotzdem
  4. Backward-kompatibel: fehlende Felder = default = jede Iteration.
     Bestehende Tests unverändert grün.

BRANCH: feature/T19-bot-loop-config
```


---

## T20 — CLI-Referenz + README auf hunt/hot/offsets/range-search aktualisieren

**Berührt:** `docs/cli-reference.md`, `README.md`. **KEINE** Crates.

```
KONTEXT-Teil (oben) + folgende Aufgabe:

HINTERGRUND: docs/cli-reference.md (417 Zeilen, T5) und README wurden vor
mehreren CLI-Features geschrieben. Es fehlen Doku-Abschnitte für:
  - spectre hunt <pid> <min> <max> [--type u32|u64|f32|f64] [--interval]
    [--bytes] [--heap-min] [--limit] [--context] [--adb]
  - spectre hot <pid> <hex> --adb [--base] [--limit] [--json]
  - spectre offsets [--check]
  - spectre search ... --min A --max B (T14)
  - spectre adb list | ping (Bluestacks-Discovery)
Zusätzlich: README-Feature-Tabelle/Beispiele ergänzen, und im README einen
Abschnitt "Live-Offset-Discovery" mit einem kurzen Ablauf: search -> dump ->
hunt -> hot (Referenz auf docs/memory-first.md und docs/afk-journey-guide.md).

AUFGABE:
  1. Ermittle die exakten Argumente aus spectre-cli/src/main.rs und den
     jeweiligen Modulen (hunt.rs etc.) — Doku NICHT aus dem Kopf erfinden.
  2. docs/cli-reference.md: für jedes neue Kommando einen Abschnitt mit
     Syntax, Optionen, Beispiel(en) — Beispiele aus echten Lauf-Helpern
     ableiten (nicht erfundene Zahlen).
  3. README: Feature-Liste + Quickstart um hunt/hot/offsets ergänzen.
  4. Markdown linten (keine kaputten Links/Code-Blöcke).
  5. DoD: docs referenzieren existierende Flags 1:1; cargo nicht nötig,
     aber git diff auf Tippfehler prüfen.

BRANCH: feature/T20-cli-docs
```
