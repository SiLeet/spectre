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
- **🔌 Pluggable Backends** — ADB (Android emulators), Native (Windows/Linux), Dump files
- **🤖 Bot Automation** — Lua-scripted bot execution with cron scheduling
- **📐 Clean Architecture** — 8 workspace crates with clear separation of concerns
- **🪶 Typed Reads** — U8–U64, I8–I64, F32/F64, strings, and pointer chain resolution
- **📄 Multi-format Output** — Table, JSON, YAML

## Commands

| Command        | Description                                  |
|----------------|----------------------------------------------|
| `spectre scan` | Scan a running game for known structures     |
| `spectre dump` | Dump raw memory bytes from an address        |
| `spectre find` | Find processes by name substring             |
| `spectre regions` | List memory regions of a process         |
| `spectre bot`  | Run a bot automation from a config file      |
| `spectre script` | Execute a Lua bot script                  |
| `spectre info` | Show version, backends, and diagnostics      |
| `spectre adb`  | ADB device management (list, ping)           |

## Quick Start

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
spectre info --diagnostics
```

## Installation

```bash
git clone https://github.com/sergej-dukart/spectre.git
cd spectre
cargo build -r

# Copy binary to PATH
cp target/release/spectre ~/.local/bin/
```

Requires Rust (≥ edition 2024). ADB backend requires `adb` on PATH.

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
| `spectre scan`  | Laufehendes Spiel nach Strukturen durchsuchen|
| `spectre dump`  | Rohe Speicherbytes ab Adresse auslesen       |
| `spectre find`  | Prozesse anhand des Namens suchen            |
| `spectre regions` | Speicherbereiche eines Prozesses auflisten |
| `spectre bot`   | Bot-Automatisierung aus Konfigurationsdatei  |
| `spectre info`  | Version, Backends und Diagnose anzeigen      |
| `spectre adb`   | ADB-Geräteverwaltung (list, ping)            |

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
spectre info --diagnostics
```

## Installation

```bash
git clone https://github.com/sergej-dukart/spectre.git
cd spectre
cargo build -r

# Binärdatei ins PATH kopieren
cp target/release/spectre ~/.local/bin/
```

Erfordert Rust (≥ Edition 2024). ADB-Backend benötigt `adb` im PATH.

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