# Getting Started with Spectre

## Prerequisites

- Rust toolchain (cargo/cargo)
- (For ADB backend) Android Debug Bridge installed and on PATH
- (For native backend) Windows or Linux host

## Installation

### From source

```bash
git clone https://github.com/sergej-dukart/spectre.git
cd spectre
cargo build -r
# Binary at target/release/spectre (or spectre.exe on Windows)
```

### Add to PATH

```bash
# Linux/macOS
export PATH="$PWD/target/release:$PATH"

# Windows (PowerShell)
$env:Path += ";" + (pwd).ToString() + "\target\release"
```

### ADB Setup

```bash
# Windows: download from Google, add to PATH
# Linux:
sudo apt install android-tools-adb
# macOS:
brew install android-tools

# Start the ADB daemon
adb start

# Verify
adb devices
```

## Quick Start: Scanning AFK Journey

### 1. Start the game

Launch AFK Journey on your emulator or PC.

### 2. Find the process

```bash
spectre find afk-journey
```

Expected output:
```
PID       NAME
--------  ----
12345     afk-journey.exe
found 1 process(es)
```

### 3. Scan for known structures

```bash
spectre scan afk-journey
```

With auto-detected PID, this loads `games/afk-journey/offsets.yaml` and scans all
rw- memory regions for the defined structures.

### 4. View scan results

```bash
spectre scan afk-journey --format json
```

Or save to a file:
```bash
spectre scan afk-journey --output results.json --format json
```

### 5. Inspect memory regions

```bash
spectre regions 12345
```

### 6. Dump raw memory

```bash
spectre dump 12345 0x7ff0000 256
```

Output shows a hex dump with ASCII sidebar:
```
07ff0000  48 65 6c 6c 6f 20 57 6f  72 6c 64 21 ...   Hello World!...
```

## ADB Mode (Android Emulator)

If the game runs in an Android emulator:

```bash
spectre adb list
# → Shows connected device(s)

spectre scan afk-journey --adb
```

Specify custom ADB host/port:
```bash
spectre scan afk-journey --adb --adb-host 192.168.1.10 --adb-port 5555
```

## Running a Bot

Bots are driven by a YAML config that references game memory fields by name
(defined in the game's `offsets.yaml`) and chains actions. A working demo lives
at `examples/bot-config.yaml`.

Minimal config:

```yaml
metadata:
  game: afk-journey
  process: afk_journey.exe
  offsets: games/afk-journey/offsets.yaml

input_backend: adb
tasks:
  - name: collect-rewards
    enabled: true
    interval_ms: 15000
    conditions: []
    actions:
      - !MemoryCheck
        field: battle_state
        op: Eq
        value: !U64 2
      - !InputClick
        x: 960
        y: 980
```

> serde_yaml deserializes enum variants using YAML tags: a `BotAction`
> variant is written as `!MemoryCheck` / `!InputClick` / `!Wait` / `!Log`,
> and a `ValueSpec` as `!U64` / `!I64` / `!F64` / `!Bytes`.

Run the bot:

```bash
spectre bot examples/bot-config.yaml
```

Validate without running:

```bash
spectre bot examples/bot-config.yaml --dry-run
```

Run once:

```bash
spectre bot my-bot.yaml --once
```

## Running a Lua Script

The `script` command executes a Lua bot script through the spectre-lua sandbox:

```bash
spectre script examples/afk-bot.lua --input-backend adb
```

Lua scripts get two modules: `spectre` (memory reads: `read_u32`,
`read_f32`, `read_string`, `find_process`, `scan`) and `bot` (input:
`click`, `swipe`, `wait`, `log`).

## Next Steps

- Read [architecture.md](architecture.md) for system design
- Read [game-integration.md](game-integration.md) to add a new game
- Browse `docs/` for detailed documentation
- Check out sample offset files under `games/`