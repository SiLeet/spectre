# Spectre

> 🔍 Mobile Game Memory Reading & Bot Framework  
> _Memory-basierte Spielanalyse und Bot-Automatisierung_

---

## 🇬🇧 / 🇩🇪 — Bilingual README

# English

## What is Spectre?

Spectre is a modular memory analysis and automation framework for mobile games. It reads
process memory (via ADB for emulators or natively on Windows/Linux), maps known data
structures using declarative YAML offset files, and executes bot strategies through Lua
scripts.

It is designed for game developers, QA engineers, and automation researchers who need
to inspect, understand, and interact with game state at runtime — **without modifying
the game binary**.

## Features

- **🔎 Memory Scanning** — Aligned pattern search across process memory regions
- **📦 Structure Mapping** — Declarative YAML offset files define game structures
- **🔌 Pluggable Backends** — ADB (Android emulators), Native (Windows/Linux), offline Dump files (`scan --dump`)
- **🤖 Bot Automation** — Lua-scripted bot execution with interval scheduling
- **📐 Clean Architecture** — 8 workspace crates with clear separation of concerns
- **🪶 Typed Reads** — U8–U64, I8–I64, F32/F64, strings, and pointer chain resolution
- **📄 Multi-format Output** — Table, JSON, YAML

## Commands

| Command        | Description                                  |
|----------------|----------------------------------------------|
| `spectre scan` | Scan a running game for known structures     |
| `spectre dump` | Dump raw memory bytes from an address        |
| `spectre dumpdiff` | Compare two raw dumps and show changed offsets (`--base`, `--json`) |
| `spectre chain` | Follow a pointer chain (`--offsets`, or raw pointers until NULL/cycle/`--depth`) |
| `spectre find` | Find processes by name substring             |
| `spectre regions` | List memory regions of a process         |
| `spectre search` | Search memory for a value; refine with `--continue`; range search with `--min`/`--max`¹ |
| `spectre hunt`¹ | Find stable candidate addresses for a value range (two reads, ranked by structure score) |
| `spectre hot`¹ | On-device byte-pattern grep over ADB; only matches cross the pipe (`--base`, `--limit`, `--json`) |
| `spectre bot`  | Run a bot automation from a config file      |
| `spectre script` | Execute a Lua bot script                  |
| `spectre info` | Show version, backends, and diagnostics      |
| `spectre offsets`¹ | Show and validate a game's offsets YAML (no game: list games) |
| `spectre serve` | Read-only web dashboard on `127.0.0.1` (`--port`, default 8787; `--rate-limit`, `--allow-origin`) |
| `spectre adb`  | ADB device management (list, ping; BlueStacks discovery¹) |

¹ Only in builds from `main`, not in release v0.3.0 (v0.4.0 is being
prepared). All flags: [docs/cli-reference.md](docs/cli-reference.md).

## Quick Start

New here? The [10-minute quickstart](examples/README.md) needs no game: it finds a changing value in a small practice process.

```bash
# Build
cargo build -r

# Find your game
spectre find afk-journey

# Scan for structures
spectre scan afk-journey

# Dump raw memory
spectre dump 12345 0x7ff0000 256

# List regions
spectre regions 12345

# Info & diagnostics
spectre info
spectre info --json
```

## Installation

**Download:** prebuilt binaries are on the
[Releases page](https://github.com/SiLeet/spectre/releases/latest):
`spectre-<version>-windows-x64.exe` (single file, no runtime needed) or the
`.zip` / `.tar.gz` packages, which also contain `games/` and `examples/`.
Run `spectre` from the folder that contains `games/` so offset files are found.

**From source:**

```bash
git clone https://github.com/SiLeet/spectre.git
cd spectre
cargo build -r

# Copy binary to PATH
cp target/release/spectre ~/.local/bin/
```

## Scanning an offline memory dump

Save a raw dump with `spectre dump`, then scan it without a live process:

```bash
spectre dump 12345 0x7ff0000 65536 --format raw --output game.dump
spectre scan afk-journey --dump game.dump --dump-base 0x7ff0000
```

`--dump-base` tells the reader the virtual address of the first byte in the
file (default `0`). Useful for forensic analysis, offset discovery, and tests.

Requires Rust (≥ edition 2024). ADB backend requires `adb` on PATH.

## Live offset discovery

Builds from `main` only (not in v0.3.0). The loop to pin down a value such as
gold on a running game, here on an Android emulator over ADB:

```bash
spectre adb list                                    # is the emulator connected?
spectre search 4321 u32 --min 259000 --max 259999 --adb   # team power, HUD shows "259K"
spectre dump 4321 0x7ff0000 65536 --adb --format raw --output before.dump
# ...change the value in the game...
spectre dump 4321 0x7ff0000 65536 --adb --format raw --output after.dump
spectre dumpdiff before.dump after.dump --base 0x7ff0000
spectre hunt 4321 9000 13000 --adb                  # gold: stable values in a range
spectre hot 4321 b8f30300 --adb                     # exact bytes, on-device grep
```

1. **search** narrows all memory to a value or range (`--continue` refines).
2. **dump** + **dumpdiff** show what changed around a candidate.
3. **hunt** ranks values in a range that stay stable between two reads.
4. **hot** finds an exact byte pattern on the device in seconds.

Why memory instead of pixels: [docs/memory-first.md](docs/memory-first.md).
Safe in-game actions to trigger a change:
[docs/afk-journey-guide.md](docs/afk-journey-guide.md). Flags and output:
[docs/cli-reference.md](docs/cli-reference.md).

## Project Structure

```
spectre/
├── spectre/              # Umbrella crate (re-exports all)
├── spectre-core/         # Types, traits, scanner engine
├── spectre-adb/          # ADB memory reader backend
├── spectre-native/       # OS-native memory reader (Win/Linux)
├── spectre-game/         # Game offset registry & YAML loader
├── spectre-bot/          # Bot execution engine & scheduler
├── spectre-lua/          # Lua scripting bindings
├── spectre-cli/          # CLI binary (user entry point)
├── games/                # Game offset YAML files
├── docs/                 # Documentation
└── examples/             # Example configs & scripts
```

## Architecture

```
CLI (spectre-cli)
  │
  ▼ uses
spectre (umbrella)
  ├── spectre-core     ← types, MemoryReader trait, scanner
  ├── spectre-adb      ← ADB backend
  ├── spectre-native   ← Windows/Linux native backend
  ├── spectre-game     ← YAML offset registry
  ├── spectre-bot      ← bot engine
  └── spectre-lua      ← Lua bindings
```

Each backend implements the `MemoryReader` trait. The `scan_memory()` engine uses it
to read process memory, enumerate regions, and find pattern matches.

## Adding a Game

Create a directory under `games/` with a YAML offset file:

```bash
mkdir -p games/my-game
touch games/my-game/offsets.yaml
```

See [docs/game-integration.md](docs/game-integration.md) for the full guide.
Game knowledge (screens, currencies, safe trigger actions) for the target
title lives in [docs/afk-journey-guide.md](docs/afk-journey-guide.md);
the memory-first automation principle is in [docs/memory-first.md](docs/memory-first.md).

## License

MIT — see [LICENSE](LICENSE).

---

# Deutsch

## Was ist Spectre?

Spectre ist ein modulares Framework zur Speicheranalyse und Automatisierung von
Handyspielen. Es liest Prozessspeicher (über ADB für Emulatoren oder nativ unter
Windows/Linux), kartiert bekannte Datenstrukturen mittels deklarativer YAML-Offset-Dateien
und führt Bot-Strategien über Lua-Skripte aus.

Entwickelt für Spieleentwickler, QA-Ingenieure und Automatisierungsforscher, die den
Spielzustand zur Laufzeit untersuchen und verstehen wollen — **ohne Änderung der
Spielbinärdatei**.

## Funktionen

- **🔎 Speicherscan** — Alignierte Mustersuche über Prozessspeicherbereiche
- **📦 Strukturabbildung** — Deklarative YAML-Offset-Dateien definieren Datenstrukturen
- **🔌 Steckbare Backends** — ADB (Android-Emulatoren), Nativ (Windows/Linux), Dump-Dateien
- **🤖 Bot-Automatisierung** — Lua-gesteuerte Bot-Ausführung mit Cron-Planung
- **📐 Saubere Architektur** — 8 Workspace-Crates mit klarer Trennung der Zuständigkeiten
- **🪶 Typisierte Lesevorgänge** — U8–U64, I8–I64, F32/F64, Zeichenketten, Pointer-Chains
- **📄 Mehrere Ausgabeformate** — Tabelle, JSON, YAML

## Befehle

| Befehl          | Beschreibung                                 |
|-----------------|----------------------------------------------|
| `spectre scan`  | Laufendes Spiel nach Strukturen durchsuchen  |
| `spectre dump`  | Rohe Speicherbytes ab Adresse auslesen       |
| `spectre dumpdiff` | Zwei Raw-Dumps vergleichen, geänderte Offsets anzeigen (`--base`, `--json`) |
| `spectre chain` | Pointer-Kette verfolgen (`--offsets`, oder rohe Pointer bis NULL/Zyklus/`--depth`) |
| `spectre find`  | Prozesse anhand des Namens suchen            |
| `spectre regions` | Speicherbereiche eines Prozesses auflisten |
| `spectre search` | Speicher nach einem Wert durchsuchen; mit `--continue` eingrenzen; Bereichssuche mit `--min`/`--max`¹ |
| `spectre hunt`¹ | Stabile Kandidaten-Adressen für einen Wertebereich finden (zwei Lesevorgänge, nach Struktur-Score sortiert) |
| `spectre hot`¹ | Byte-Muster per grep auf dem Gerät suchen (ADB); nur Treffer gehen über die Leitung (`--base`, `--limit`, `--json`) |
| `spectre bot`   | Bot-Automatisierung aus Konfigurationsdatei  |
| `spectre script` | Lua-Bot-Skript ausführen                    |
| `spectre info`  | Version, Backends und Diagnose anzeigen      |
| `spectre offsets`¹ | Offsets-YAML eines Spiels anzeigen und prüfen (ohne Spiel: Spiele auflisten) |
| `spectre serve` | Read-only-Web-Dashboard auf `127.0.0.1` (`--port`, Standard 8787; `--rate-limit`, `--allow-origin`) |
| `spectre adb`   | ADB-Geräteverwaltung (list, ping; BlueStacks-Erkennung¹) |

¹ Nur in Builds aus `main`, nicht im Release v0.3.0 (v0.4.0 ist in
Vorbereitung). Alle Optionen: [docs/cli-reference.md](docs/cli-reference.md)
(englisch).

## Kurzanleitung

```bash
# Bauen
cargo build -r

# Spielprozess finden
spectre find afk-journey

# Nach Strukturen scannen
spectre scan afk-journey

# Rohen Speicher auslesen
spectre dump 12345 0x7ff0000 256

# Speicherbereiche auflisten
spectre regions 12345

# Info & Diagnose
spectre info
spectre info --json
```

## Installation

**Download:** fertige Programme gibt es auf der
[Releases-Seite](https://github.com/SiLeet/spectre/releases/latest):
`spectre-<version>-windows-x64.exe` (eine Datei, keine Laufzeit nötig) oder
die `.zip`- / `.tar.gz`-Pakete, die zusätzlich `games/` und `examples/`
enthalten. `spectre` aus dem Ordner starten, der `games/` enthält, damit die
Offset-Dateien gefunden werden.

**Aus dem Quellcode:**

```bash
git clone https://github.com/SiLeet/spectre.git
cd spectre
cargo build -r

# Binärdatei ins PATH kopieren
cp target/release/spectre ~/.local/bin/
```

Erfordert Rust (≥ Edition 2024). ADB-Backend benötigt `adb` im PATH.

## Live-Offset-Discovery

Nur in Builds aus `main` (nicht in v0.3.0). Der Ablauf, um einen Wert wie
Gold im laufenden Spiel festzunageln, hier auf einem Android-Emulator über ADB:

```bash
spectre adb list                                    # ist der Emulator verbunden?
spectre search 4321 u32 --min 259000 --max 259999 --adb   # Teamstärke, HUD zeigt "259K"
spectre dump 4321 0x7ff0000 65536 --adb --format raw --output before.dump
# ...Wert im Spiel ändern...
spectre dump 4321 0x7ff0000 65536 --adb --format raw --output after.dump
spectre dumpdiff before.dump after.dump --base 0x7ff0000
spectre hunt 4321 9000 13000 --adb                  # Gold: stabile Werte im Bereich
spectre hot 4321 b8f30300 --adb                     # exakte Bytes, grep auf dem Gerät
```

1. **search** grenzt den Speicher auf einen Wert oder Bereich ein (`--continue` verfeinert).
2. **dump** + **dumpdiff** zeigen, was sich um einen Kandidaten herum geändert hat.
3. **hunt** sortiert Werte eines Bereichs, die zwischen zwei Lesevorgängen stabil bleiben.
4. **hot** findet ein exaktes Byte-Muster in Sekunden direkt auf dem Gerät.

Warum Speicher statt Pixel: [docs/memory-first.md](docs/memory-first.md).
Sichere Spielaktionen, die einen Wert ändern:
[docs/afk-journey-guide.md](docs/afk-journey-guide.md). Optionen und Ausgaben:
[docs/cli-reference.md](docs/cli-reference.md) (englisch).

## Projektstruktur

```
spectre/
├── spectre/              # Kapsel-Crate (exportiert alle Sub-Crates)
├── spectre-core/         # Typen, Traits, Scan-Engine
├── spectre-adb/          # ADB-Speicherleser-Backend
├── spectre-native/       # OS-nativer Speicherleser (Win/Linux)
├── spectre-game/         # Spiele-Offset-Register & YAML-Lader
├── spectre-bot/          # Bot-Ausführungs-Engine & Scheduler
├── spectre-lua/          # Lua-Skript-Bindungen
├── spectre-cli/          # CLI-Binär (Benutzereinstiegspunkt)
├── games/                # Spiel-Offset-YAML-Dateien
├── docs/                 # Dokumentation
└── examples/             # Beispielkonfigurationen & -skripte
```

## Architektur

```
CLI (spectre-cli)
  │
  ▼ nutzt
spectre (umbrella)
  ├── spectre-core     ← Typen, MemoryReader-Trait, Scanner
  ├── spectre-adb      ← ADB-Backend
  ├── spectre-native   ← Windows/Linux nat. Backend
  ├── spectre-game     ← YAML-Offset-Register
  ├── spectre-bot      ← Bot-Engine
  └── spectre-lua      ← Lua-Bindungen
```

Jedes Backend implementiert das `MemoryReader`-Trait. Die `scan_memory()`-Engine nutzt
es, um Prozessspeicher zu lesen, Bereiche aufzulisten und Muster zu finden.

## Ein Spiel hinzufügen

Erstelle ein Verzeichnis unter `games/` mit einer YAML-Offset-Datei:

```bash
mkdir -p games/my-game
touch games/my-game/offsets.yaml
```

Siehe [docs/game-integration.md](docs/game-integration.md) für die vollständige Anleitung (englisch).

## Lizenz

MIT — siehe [LICENSE](LICENSE).

---

Made by [Sergej Dukart](https://github.com/sergej-dukart).