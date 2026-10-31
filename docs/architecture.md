# Spectre Architecture

## Overview

Spectre is a modular memory reading and game automation framework built for mobile games running on emulators (ADB) or natively (Windows/Linux). It reads process memory, maps known structures using offset YAML files, and executes bot strategies via Lua scripts.

```
┌─────────────────────────────────────────────────────────────┐
│                    Spectre CLI (spectre-cli)                │
│         scan  dump  find  regions  bot  info  adb          │
└────────────────────────┬────────────────────────────────────┘
                         │
    ┌────────────────────┴────────────────────────────────────┐
    │                 spectre (umbrella crate)                │
    │           re-exports all subcrates for convenience     │
    └──────┬──────────┬──────────┬──────────┬────────────────┘
           │          │          │          │
    ┌──────┴──┐ ┌─────┴──┐ ┌────┴───┐ ┌───┴───────┐
    │ core   │ │ adb   │ │native │ │ game     │
    │ types  │ │ ADB   │ │Win/   │ │ offset   │
    │ reader │ │ mem   │ │Linux  │ │ registry │
    │ scanner│ │ reader│ │reader │ │ YAML     │
    └────────┘ └───────┘ └───────┘ └──────────┘
              ┌──────────┐ ┌──────────┐
              │   bot    │ │   lua    │
              │execution │ │ scripting│
              │scheduling│ │ bindings │
              └──────────┘ └──────────┘
```

## Layer Architecture

### 1. spectre-core — Types & Engine

The foundation crate. Defines all shared types (`ProcessInfo`, `MemoryRegion`, `ScanPattern`, 
`StructDef`, `GameOffsets`, etc.) and the abstract `MemoryReader` trait that every backend
implements. The scanner engine (`scan_memory`) consumes patterns and produces match reports.

**Key traits:**
- `MemoryReader` — read bytes, discover processes, enumerate memory regions, resolve pointer chains
- `ScanPattern` / `ScanValue` — declarative pattern matching

### 2. spectre-adb — Android Debug Bridge Backend

Connects to Android emulators (or real devices) via ADB. Uses `/proc/<pid>/mem` on the device
or the ADB `shell` protocol to read guest process memory.

**Key behaviours:**
- Lists ADB devices
- Attaches to a specific PID on the device
- Reads memory through ADB shell commands (e.g. `dd`, `xxd`, custom ptrace-based reader)

### 3. spectre-native — OS-native Backend

Reads process memory directly on the host OS:
- **Windows:** Uses the Windows process manipulation API (`ReadProcessMemory`)
- **Linux:** Reads from `/proc/<pid>/mem`

### 4. spectre-game — Game Offset Registry

Loads YAML-based game offset files that define known data structure layouts. Each game
has its own directory under `games/` containing:
- `offsets.yaml` — structure definitions with field names, types, and offsets
- `README.md` — game-specific notes and version compatibility

**Offset file format:**
```yaml
game: "afk-journey"
version: "1.0.45"
structures:
  - name: "PlayerState"
    base_offset: 0x12345678
    fields:
      - name: "player_id"
        field_type: U32
        offset: 0x00
        desc: "Unique player identifier"
      - name: "level"
        field_type: U32
        offset: 0x04
        desc: "Current player level"
      - name: "exp"
        field_type: U64
        offset: 0x08
        desc: "Current experience points"
      - name: "nickname"
        field_type: String(32)
        offset: 0x10
        desc: "Player display name"
```

The type key may also be written `type`, and type names are
case-insensitive (`u32`, `string:32`); see
[game-integration.md](game-integration.md#field-types).

### 5. spectre-bot — Bot Execution Engine

Runs configurable bot scripts with scheduling support. A bot is defined in a YAML config:
- Game target
- Action sequences (Lua script references)
- Schedules (cron-like timers)
- Condition checks

### 6. spectre-lua — Lua Scripting Bindings

Bridges Spectre types into Lua for runtime bot automation. Uses `mlua` for the Lua VM.

### 7. spectre-cli — Command-line Interface

The user-facing entry point built with `structopts`. Commands:
- `scan` — scan game memory for known structures
- `dump` — raw memory dump from an address
- `find` — discover processes by name
- `regions` — enumerate memory regions
- `bot` — run bot automation from config
- `info` — version, backends, diagnostics
- `adb list` / `adb ping` — ADB device management

## Data Flow

```
1. User runs: spectre scan afk-journey

2. CLI resolves PID (auto-detect or --pid)
   └→ Determines backend (ADB or native)

3. Loads games/afk-journey/offsets.yaml
   └→ Creates ScanPattern[] from StructDef[]

4. Creates MemoryReader (ADB or native)
   └→ Enumerates memory regions
   └→ Filters to writable/readable ranges

5. Executes scan_memory()
   └→ For each pattern:
       └→ Read memory in batches
       └→ Try match at aligned addresses
       └→ Collect matches

6. Outputs results (table/JSON/YAML)
```

## Key Design Decisions

- **Pluggable backends:** The `MemoryReader` trait allows adding new backends (e.g. QEMU, GDB) without changing the scan engine.
- **Declarative patterns:** Game structures are defined as YAML, not code. Adding a new game means writing a YAML file.
- **Lua automation:** Bot logic lives in Lua scripts loaded at runtime — no recompilation needed.
- **Workspace crates:** Each concern has its own crate for independent compilation, testing, and reuse.