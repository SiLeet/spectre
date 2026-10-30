# Spectre CLI Reference

Complete reference for the `spectre` command-line tool. Help texts below are
copied from `spectre <command> --help` (version 0.1.0).

## Overview

```
spectre [FLAGS] [SUBCOMMAND]
```

| Global flag | Description |
|-------------|-------------|
| `-h`, `--help` | Prints help information |
| `-V`, `--version` | Prints version information |
| `-v`, `--verbose` | Enable verbose logging (repeat for more detail) |

| Subcommand | Description |
|------------|-------------|
| [`scan`](#scan) | Scan a running game for known data structures |
| [`dump`](#dump) | Dump raw memory bytes from a process address |
| [`dumpdiff`](#dumpdiff) | Compare two raw dump files and show changed offsets |
| [`chain`](#chain) | Follow a pointer chain from an address |
| [`find`](#find) | Find processes by name |
| [`regions`](#regions) | List memory regions of a process |
| [`search`](#search) | Search memory for a value; refine previous results |
| [`bot`](#bot) | Run a bot automation script |
| [`script`](#script) | Execute a Lua bot script |
| [`info`](#info) | Show version and available backends |
| [`serve`](#serve) | Start the read-only web dashboard (127.0.0.1 only) |
| [`adb`](#adb) | ADB device management |

**Backends.** Commands that read memory use the native backend
(Windows `ReadProcessMemory`, Linux `/proc/<pid>/mem`) unless `--adb` is
given, which reads through `adb` from an Android emulator or device.
`adb` must be on `PATH` for that.

**Numbers.** Addresses and other numeric arguments accept hex with a `0x`
prefix (`0x7ff0000`) or decimal (`134152192`).

---

## scan

Scan a running game for known data structures, using the game's offset YAML.

```
spectre scan [FLAGS] [OPTIONS] <game>
```

| Argument | Description |
|----------|-------------|
| `<game>` | Game name (e.g. `"afk-journey"`). Loads the corresponding offset file |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend instead of native |
| `--adb-host <adb-host>` | ADB host (default: localhost) |
| `--adb-port <adb-port>` | ADB port (default: 5555) |
| `--dump <dump>` | Scan an offline memory dump file instead of a live process |
| `--dump-base <dump-base>` | Virtual address of the first byte in the dump file (default: 0) |
| `-f`, `--format <format>` | Output format: table (default), json, yaml |
| `-o`, `--offsets <offsets>` | Path to a custom offsets YAML file |
| `-O`, `--output <output>` | Write results to this file instead of stdout |
| `-p`, `--pid <pid>` | PID of the target process (auto-detect if omitted) |

Offsets are looked up at `games/<game>/offsets.yaml` unless `--offsets` is given.

```bash
spectre scan afk-journey
spectre scan afk-journey --pid 12345 --format json --output scan.json
spectre scan afk-journey --adb --adb-host 127.0.0.1 --adb-port 5555
```

## dump

Dump raw memory bytes from a process address.

```
spectre dump [FLAGS] [OPTIONS] <pid> <address> <size>
```

| Argument | Description |
|----------|-------------|
| `<pid>` | Process ID |
| `<address>` | Starting address (hex with 0x prefix, or decimal) |
| `<size>` | Number of bytes to dump |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend |
| `-f`, `--format <format>` | Output format: hex (default), raw, ascii |
| `-o`, `--output <output>` | Output file (default: stdout) |

```bash
spectre dump 12345 0x7ff0000 256
spectre dump 12345 0x7ff0000 65536 --format raw --output before.dump
```

## dumpdiff

Compare two raw dump files (as written by `spectre dump --format raw`) and
show which byte ranges changed. Changes separated by at most 16 unchanged
bytes are merged into one region. If the files differ in length, the extra
tail is reported as its own region.

```
spectre dumpdiff [FLAGS] [OPTIONS] <old> <new>
```

| Argument | Description |
|----------|-------------|
| `<old>` | Older raw dump file (e.g. from `spectre dump --format raw`) |
| `<new>` | Newer raw dump file of the same memory range |

| Flag / option | Description |
|---------------|-------------|
| `--json` | Output as JSON (full hex, with file offset and address per region) |
| `--base <base>` | Virtual address of the first byte in both dumps; added to printed offsets [default: 0] |

Table output truncates each side to 32 bytes; JSON output is never truncated.
A side that does not exist (length-mismatch tail) prints as `-` in the table
and `""` in JSON.

```bash
spectre dumpdiff before.dump after.dump --base 0x7ff0000
spectre dumpdiff before.dump after.dump --base 0x7ff0000 --json > diff.json
```

Example output:

```
3 changed region(s), 75 changed byte(s)  (old: 512 bytes, new: 518 bytes)
0x7FF0010  old: 10 11 12 13 14 15 16 17 18  new: e8 03 00 00 14 15 16 17 63
...
0x7FF0200  old: -  new: ee ee ee ee ee ee
```

## chain

Follow a pointer chain from an address and print every dereference.

```
spectre chain [FLAGS] [OPTIONS] <address> (--pid <pid> | --name <name>)
```

| Argument | Description |
|----------|-------------|
| `<address>` | Start address (hex with 0x prefix, or decimal) |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend |
| `--big-endian` | Read pointers as big-endian (default: little-endian) |
| `--json` | Output as JSON |
| `-p, --pid <pid>` | PID of the target process (auto-detected from --name if omitted) |
| `-n, --name <name>` | Process name substring used to auto-detect the PID when --pid is not given |
| `--depth <depth>` | Maximum number of dereferences when --offsets is not given [default: 16] |
| `--offsets <offsets>` | Comma-separated offsets, each added before a dereference (e.g. 0x10,0x8); the start address itself is not dereferenced and the last address is read but not followed. For a Cheat Engine path prepend a 0 offset. Without it, raw pointers are followed until NULL, a cycle, unreadable memory, or --depth |

One of `--pid` or `--name` is required; with `--name` the first matching
process is used (a warning is logged if several match).

Two modes:

- **With `--offsets`** the chain is resolved with the semantics of
  `MemoryReader::resolve_ptr_chain`: each offset is added *before* its
  dereference, the start address itself is not dereferenced, and the last
  `pointer + offset` is the result (it is read, so its u64 value is shown
  too, but not followed):

  ```
  <address> +o0 -> *a0 = p1 ; p1 +o1 -> *a1 = p2 ; ... ; p(n-1) +o(n-1) = resolved
  ```

  That is `[[address+o0]+o1]+..`. This is **not** the Cheat Engine
  convention: Cheat Engine reads the pointer at the base first
  (`[[base]+o0]+o1`). To resolve a Cheat Engine path `base -> [o0, o1, ..]`,
  add a leading `0` offset: `--offsets 0,o0,o1,..`.

  A NULL intermediate pointer stops the walk instead of reading near 0.
- **Without `--offsets`** raw pointers are followed (`*start`, `**start`, ...)
  until a value is 0, a pointer repeats (cycle), memory is unreadable, or
  `--depth` reads were made. `resolved` is the last address that could be
  read (the deepest link).

`stop` says why the walk ended: `complete` (all offsets applied), `null`,
`max_depth`, `unreadable` (with the failing address and the read error) or
`cycle` (with the repeated address). If the chain could not be resolved,
`resolved` is `-` (`null` in JSON) and the exit code is still 0 — except when
not even the first read succeeds (wrong PID, missing permissions, unmapped
start address): then `chain` prints the error and exits with 1, like `dump`.

```bash
spectre chain 0x7ff0000 --pid 12345 --offsets 0x10,0x8,0x30
spectre chain 0x7ff0000 --name game.exe --depth 8 --json
spectre chain 0x12c0000 -p 4321 --adb --offsets 0x18,0x4
# Cheat Engine path 0x7ff0000 -> [0x10, 0x8, 0x30]:
spectre chain 0x7ff0000 --pid 12345 --offsets 0,0x10,0x8,0x30
```

Example output:

```
pointer chain from 0x7ff0000 (pid 12345)
  [0] 0x7ff0000 + 0x10 -> *0x7ff0010 = 0x2a10000
  [1] 0x2a10000 + 0x8 -> *0x2a10008 = 0x2b20000
  [2] 0x2b20000 + 0x30 -> *0x2b20030 = 0x3e8
stop:     complete (all offsets applied)
resolved: 0x2b20030
```

Walks with `--offsets` always print steps in this `pointer + offset ->`
form, also for a `0` offset. Raw walks (no `--offsets`) print steps as
`[i] *0x7ff0000 = 0x2a10000`. When the walk stops at unreadable memory, an
`error:` line with the read error follows the `stop:` line.
JSON output has `pid`, `base`, `offsets`, `steps` (`pointer`, `offset`,
`address`, `value`), `stop` (`reason`, plus `address` and `error` for
`unreadable`, `address` for `cycle`) and `resolved`; all addresses are `0x`
hex strings.

## find

Find processes by name.

```
spectre find [FLAGS] <name>
```

| Argument | Description |
|----------|-------------|
| `<name>` | Process name substring to search for |

| Flag | Description |
|------|-------------|
| `--adb` | Use ADB backend |
| `--json` | Output as JSON |

```bash
spectre find afk-journey
spectre find journey --adb --json
```

## regions

List memory regions of a process.

```
spectre regions [FLAGS] [OPTIONS] <pid>
```

| Argument | Description |
|----------|-------------|
| `<pid>` | Process ID |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend |
| `--json` | Output as JSON |
| `-f`, `--filter <filter>` | Filter by permission substring (e.g. "rw", "r--") |

```bash
spectre regions 12345
spectre regions 12345 --filter rw --json
```

## search

Search all readable memory of a process for a value, then narrow the
candidates down with `--continue` (Cheat-Engine style).

```
spectre search [FLAGS] [OPTIONS] <pid> <type> <value>
```

| Argument | Description |
|----------|-------------|
| `<pid>` | Process ID |
| `<type>` | Value type: u8/u16/u32/u64/i8/i16/i32/i64/f32/f64 |
| `<value>` | Value to find (decimal, hex with 0x, or float) |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend |
| `--continue` | Refine the previous search results instead of scanning all memory |
| `--json` | Output as JSON |
| `--limit <limit>` | Stop after N results (0 = unlimited) [default: 0] |
| `--state <state>` | State file for previous/next search (default: .spectre-search.json) |

Matches are checked at the value's natural alignment, little-endian. Every
run writes the resulting addresses to the state file; `--continue` re-reads
only those addresses and keeps the ones that now hold the new value.

> **Current limitations.** The help text says `<pid>` can be omitted with
> `--continue`, but the refine step needs the PID to re-read memory, so
> always pass it. `--json` is accepted but output is currently always plain
> text (one address per line plus a summary line).

```bash
spectre search 12345 u32 42 --limit 100
spectre search 12345 u32 55 --continue
spectre search 12345 f32 98.5 --state hp-search.json
```

## bot

Run a bot from a YAML configuration file.

```
spectre bot [FLAGS] [OPTIONS] <config>
```

| Argument | Description |
|----------|-------------|
| `<config>` | Path to bot configuration YAML file |

| Flag / option | Description |
|---------------|-------------|
| `--dry-run` | Dry run — validate config without executing |
| `--once` | Run once and exit (no scheduling loop) |
| `-n`, `--name <name>` | Bot instance name (for multi-bot setups) |

Without `--once`, the CLI runs the actions of every enabled task, then
sleeps `default_interval_ms`, and repeats.

> **Current limitation.** The CLI loop does not use the bot crate's
> `TaskScheduler` yet: per-task `interval_ms` and task-level `conditions`
> are shown by `--dry-run` but not applied. Use `!MemoryCheck` / `!Condition`
> actions inside a task to guard its steps.

```bash
spectre bot examples/bot-config.yaml --dry-run
spectre bot examples/bot-config.yaml --once
spectre bot examples/bot-config.yaml --name farm-1
```

See [Bot configuration](#bot-configuration) below for the file format.

## script

Execute a Lua bot script.

```
spectre script [OPTIONS] <script>
```

| Argument | Description |
|----------|-------------|
| `<script>` | Path to a Lua script file |

| Option | Description |
|--------|-------------|
| `--input-backend <input-backend>` | Input backend for bot.* actions (default: adb) |

```bash
spectre script examples/afk-bot.lua
```

## info

Show version and available backends.

```
spectre info [FLAGS]
```

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON |

Prints the version, the native backend kind, whether `adb` is on `PATH`,
and the games found under `games/`.

```bash
spectre info
spectre info --json
```

## serve

Start the read-only web dashboard (127.0.0.1 only).

```
spectre serve [FLAGS] [OPTIONS]
```

| Flag / option | Description |
|---------------|-------------|
| `-p`, `--port <port>` | Port to listen on; always bound to 127.0.0.1 (0 = pick a free port) [default: 8787] |
| `--adb` | Use ADB backend instead of native |
| `--adb-host <adb-host>` | ADB host (default: localhost) |
| `--adb-port <adb-port>` | ADB port (default: 5555) |

Prints the dashboard URL (`http://127.0.0.1:<port>/`) and serves until
Ctrl+C. The server only binds the loopback interface; there is no `--host`
option. The browser UI is embedded in the binary (no CDN, works offline) and
offers a process list with filter, the region table of the selected process,
a read form and a value search.

All endpoints are read-only `GET` requests returning
`{ "ok": true, "data": ... }` or `{ "ok": false, "error": "..." }`:

| Endpoint | Description |
|----------|-------------|
| `/api/info` | Version, backend kind and request limits |
| `/api/processes[?name=S]` | All processes, or those whose name contains `S` |
| `/api/regions?pid=N[&perms=S]` | Memory regions (optionally filtered by permission substring) |
| `/api/read?pid=N&addr=A&type=T[&size=S][&endian=little\|big]` | Read one value; `type` is `u8`..`u64`, `i8`..`i64`, `f32`, `f64`, `string` or `bytes`; `size` (string/bytes) defaults to 64, max 4096 |
| `/api/search?pid=N&type=T&value=V[&limit=L][&endian=little\|big]` | Exact-value search in writable regions; `limit` defaults to 1000, max 10000 |

Invalid parameters return HTTP 400, backend failures (unreadable address,
unknown pid, ADB offline) HTTP 502. Requests addressed to a non-loopback
`Host` or coming from another website (`Origin` / `Sec-Fetch-Site`) are
refused with HTTP 403 (DNS-rebinding protection); at most two searches run at
once (HTTP 429 otherwise). See `spectre-web/README.md` for details.

```bash
spectre serve                 # http://127.0.0.1:8787/
spectre serve --port 0        # pick a free port, print it
spectre serve --adb           # inspect an Android emulator via ADB
```

## adb

ADB device management.

```
spectre adb <SUBCOMMAND>
```

| Subcommand | Description |
|------------|-------------|
| `list` | List connected ADB devices |
| `ping [serial]` | Ping an ADB device (serial optional — pings the default device if omitted) |

```bash
spectre adb list
spectre adb ping emulator-5554
```

---

## Workflow: offline analysis

Dump a memory range once, then scan or compare it without the game running.

```bash
# 1. Find the process and a region worth dumping
spectre find afk-journey
spectre regions 12345 --filter rw

# 2. Save the range as a raw dump
spectre dump 12345 0x7ff0000 65536 --format raw --output game.dump

# 3. Scan the dump for known structures
spectre scan afk-journey --dump game.dump --dump-base 0x7ff0000
```

`--dump-base` must be the address you passed to `dump`, so reported match
addresses line up with the live process.

## Workflow: offset discovery

**Value search (live).** Use when you know the value shown in the game.

```bash
spectre search 12345 u32 42 --limit 100   # level is 42
# ...level up in the game...
spectre search 12345 u32 43 --continue    # keep addresses that now hold 43
# repeat until one address remains
```

**Dump diff (offline).** Use when you don't know the exact value, only that
it changed.

```bash
spectre dump 12345 0x7ff0000 65536 --format raw --output before.dump
# ...spend gold in the game...
spectre dump 12345 0x7ff0000 65536 --format raw --output after.dump
spectre dumpdiff before.dump after.dump --base 0x7ff0000
```

Once you have an address, express it relative to a stable base and add it to
`games/<game>/offsets.yaml` — see [game-integration.md](game-integration.md).

## Bot configuration

A complete example lives in [`examples/bot-config.yaml`](../examples/bot-config.yaml).

| Top-level key | Default | Description |
|---------------|---------|-------------|
| `tasks` | `[]` | List of tasks |
| `default_interval_ms` | `500` | Sleep between bot loop iterations |
| `input_backend` | `adb` | Input backend for click/swipe actions (only `adb` works end-to-end) |
| `memory_poll_ms` | `100` | Memory poll interval |
| `enabled` | `true` | Master switch |
| `metadata` | – | `game`, `process`, `offsets` (path to the offsets YAML used to resolve field names) |

Each task has `name`, `enabled`, `conditions` and `actions` (required),
plus either `interval_ms` (`0` or omitted = `default_interval_ms`) or a
cron-style `schedule` such as `"0 */6 * * *"` (minute hour day month
weekday; supports `*`, values, ranges, `*/n` steps and lists). A bad
`schedule` is rejected when the config is loaded. `conditions` are guard
conditions for the bot crate's scheduler; see the limitation under
[`bot`](#bot) — the CLI loop validates `schedule` but does not honour it yet.

Actions and values are Rust enums and are written with **YAML tags**:

| Action | Fields |
|--------|--------|
| `!MemoryCheck` | `field`, `op`, `value` |
| `!InputClick` | `x`, `y` |
| `!InputSwipe` | `x1`, `y1`, `x2`, `y2`, `millis` |
| `!Wait` | `millis` |
| `!Loop` | `count`, `array` (list of actions) |
| `!Condition` | `cond` (a condition), `then_` (action), `else_` (optional action) |
| `!ScriptHook` | `name` |
| `!Log` | `message`, `level` (`Info`, `Warn`, `Error`, `Debug`) |

Comparison operators (`op`): `Eq`, `Neq`, `Gt`, `GtEq`, `Lt`, `LtEq`.

Values: `!U64 200`, `!I64 -5`, `!F64 0.5`, `!Bytes [0x01, 0x02]`.

```yaml
tasks:
  - name: collect-rewards
    enabled: true
    interval_ms: 15000
    conditions:
      - field: gold
        op: Gt
        value: !I64 100
    actions:
      - !MemoryCheck
        field: battle_state
        op: Eq
        value: !U64 2
      - !InputClick
        x: 960
        y: 980
      - !Wait
        millis: 500
      - !Log
        message: "collected rewards"
        level: Info
```
