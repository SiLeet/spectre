# Getting Started with Spectre

> **TL;DR**
>
> ```bash
> cargo build -r                       # or download a release, see below
> spectre find <process-name>          # -> PID
> spectre search <pid> u32 <value>     # then change the value and add --continue
> ```
>
> No game at hand? The [10-minute quickstart](../examples/README.md) walks
> through the whole find / search / dump / dumpdiff workflow on a small
> practice process.

## Prerequisites

- Either a prebuilt release binary, or a Rust toolchain (<https://rustup.rs>)
  to build from source — on Windows also the Visual Studio C++ Build Tools
- (For ADB backend) Android Debug Bridge installed and on PATH
- (For native backend) Windows or Linux host

## Installation

### Download

Prebuilt binaries are on the
[Releases page](https://github.com/SiLeet/spectre/releases/latest):
`spectre-v0.2.0-windows-x64.exe` (single file) or the `.zip` / `.tar.gz`
packages, which also contain `games/` and `examples/`. Run `spectre` from the
folder that contains `games/` so offset files are found. The v0.2.0 packages
predate the quickstart's practice files (`practice-target.ps1`,
`practice_target.py`, `practice-offsets.yaml`, `practice.lua`); get those from
the repository's `examples/` folder until the next release, as described in
the [quickstart](../examples/README.md#step-0--get-spectre).

### From source

```bash
git clone https://github.com/SiLeet/spectre.git
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
adb start-server

# Verify
adb devices
```

## Quick Start: Scanning AFK Journey

### 1. Start the game

Launch AFK Journey on your emulator or PC.

### 2. Find the process

```bash
spectre find journey
```

The name is a substring match. Example output:
```
PID       NAME
12345     afk_journey.exe
found 1 process(es)
```

### 3. Scan for known structures

```bash
spectre scan afk-journey --pid 12345
```

This loads `games/afk-journey/offsets.yaml` and scans all rw- memory regions
for the defined structures. Without `--pid`, spectre tries to auto-detect the
process from the game name and asks for `--pid` if that fails.

> **0.2.0:** the bundled `games/afk-journey/offsets.yaml` holds placeholder
> offsets and does not load in `scan` yet (`missing field 'type'`). Pass your
> own offsets file with `--offsets`; `examples/practice-offsets.yaml` shows
> the format `scan` reads. To find offsets in the first place, use
> `spectre search` and `spectre dumpdiff` — see the
> [quickstart](../examples/README.md).

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
0000000007ff0000  48 65 6c 6c 6f 20 57 6f 72 6c 64 21 00 00 00 00   Hello World!....
...
```

Add `--format raw --output before.dump` to save the bytes for
`spectre dumpdiff` or `spectre scan --dump`.

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

The bot needs the process named in `metadata.process` (or `metadata.pid`) to
be running. In 0.2.0 the CLI loop runs every enabled task's actions each
round and then sleeps `default_interval_ms`; per-task `interval_ms`,
`conditions` and cron `schedule` are validated but not applied yet.

## Running a Lua Script

The `script` command executes a Lua bot script through the spectre-lua sandbox:

```bash
spectre script examples/afk-bot.lua --input-backend adb
```

`afk-bot.lua` waits for `afk_journey.exe` and needs `adb` for its clicks;
`examples/practice.lua` runs without a game or adb (see the
[quickstart](../examples/README.md), step 4).

Lua scripts get two modules: `spectre` (memory reads: `read_u32`,
`read_u64`, `read_i32`, `read_f32`, `read_string`, `read_fields`,
`regions`, `find_process`, `scan`) and `bot` (input: `click`, `swipe`,
`wait`, `log`).

## Next Steps

- Do the [10-minute quickstart](../examples/README.md) with the practice target
- Read [architecture.md](architecture.md) for system design
- Read [game-integration.md](game-integration.md) to add a new game
- Browse `docs/` for detailed documentation
- Check out sample offset files under `games/`