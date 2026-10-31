# Spectre CLI Reference

Complete reference for the `spectre` command-line tool. Help texts below are
copied from `spectre <command> --help` (version 0.3.0, built from `main`).

> **Not in a release yet.** The latest release, v0.3.0, does not have
> [`hunt`](#hunt), [`hot`](#hot), [`offsets`](#offsets), the range search
> `search --min/--max`, or the adb binary and BlueStacks discovery described
> under [`adb`](#adb). They are only in builds from `main` (v0.4.0 is being
> prepared); these sections are marked *main only*.

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
| [`hunt`](#hunt) | Find candidate addresses for a value range (offset discovery) |
| [`hot`](#hot) | Search a byte pattern on the device; only matches cross adb |
| [`bot`](#bot) | Run a bot automation script |
| [`script`](#script) | Execute a Lua bot script |
| [`info`](#info) | Show version and available backends |
| [`offsets`](#offsets) | Show and validate a game's offsets YAML (no game: list games) |
| [`serve`](#serve) | Start the read-only web dashboard (127.0.0.1 only) |
| [`adb`](#adb) | ADB device management |

**Backends.** Commands that read memory use the native backend
(Windows `ReadProcessMemory`, Linux `/proc/<pid>/mem`) unless `--adb` is
given, which reads through `adb` from an Android emulator or device.
v0.3.0 needs `adb` on `PATH` for that; builds from `main` also use
`%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` or BlueStacks NXT's
`HD-Adb.exe`, on Windows even ahead of `PATH` (see [adb binary](#adb)).

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
spectre search [FLAGS] [OPTIONS] <pid> <type> --min <min> --max <max>
```

| Argument | Description |
|----------|-------------|
| `<pid>` | Process ID |
| `<type>` | Value type: u8/u16/u32/u64/i8/i16/i32/i64/f32/f64 |
| `<value>` | Value to find (decimal, hex with 0x, or float); omit when using `--min/--max` |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend |
| `--continue` | Refine the previous search results instead of scanning all memory |
| `--json` | Output as JSON |
| `--limit <limit>` | Stop after N results (0 = unlimited) [default: 0] |
| `--min <min>` | Range search: lower bound, inclusive (use with --max instead of <value>) |
| `--max <max>` | Range search: upper bound, inclusive (use with --min instead of <value>) |
| `--state <state>` | State file for previous/next search (default: .spectre-search.json) |

Matches are checked at the value's natural alignment, little-endian. Every
run writes the resulting addresses to the state file; `--continue` re-reads
only those addresses and keeps the ones that now hold the new value.

**Range search** (*main only*). When the game only shows a rounded value
("259K"), pass
`--min`/`--max` instead of `<value>`: every slot is decoded as `<type>` and
kept when `min <= value <= max`. Bounds are decimal (negative allowed for
signed types, e.g. `--min -5`), 0x-hex, or floats for `f32/f64`; they must fit
the type and `min` must not exceed `max`. NaN never matches. `string` is not
supported. `--continue` with `--min/--max` keeps the previous addresses whose
current value is in the range. Unreadable regions are skipped.

> **Current limitations.** The help text says `<pid>` can be omitted with
> `--continue`, but the refine step needs the PID to re-read memory, so
> always pass it. `--json` is accepted but output is currently always plain
> text (one address per line plus a summary line).

```bash
spectre search 12345 u32 42 --limit 100
spectre search 12345 u32 55 --continue
spectre search 12345 f32 98.5 --state hp-search.json
spectre search 12345 u32 --min 259000 --max 259999
spectre search 12345 u32 --min 259000 --max 259999 --continue
```

## hunt

*Main only.* Find candidate addresses for a value range without knowing the
exact value. `hunt` reads the largest heaps twice, `--interval` seconds
apart, and keeps every aligned slot whose value lies in `<min>..=<max>` and
is identical in both reads (stable values, not allocator churn). The
candidates are ranked by a structure score, so object-table IDs land last.

```
spectre hunt [FLAGS] [OPTIONS] <pid> <min> <max>
```

| Argument | Description |
|----------|-------------|
| `<pid>` | Target process ID |
| `<min>` | Lower bound of the numeric range to scan (decimal or 0x hex) |
| `<max>` | Upper bound of the numeric range to scan (decimal or 0x hex) |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend instead of native |
| `--adb-host <adb-host>` | ADB host (default: 127.0.0.1) |
| `--adb-port <adb-port>` | ADB port (default: 5555) |
| `--bytes <bytes>` | Bytes per heap to inspect (default 8 MiB per heap, top heaps only) [default: 8388608] |
| `--context` | Print the surrounding 32 bytes of each candidate |
| `--heap-min <heap-min>` | Only scan the heap(s) whose start address is at least this (hex) |
| `--interval <interval>` | Seconds between the two dumps (default 5) [default: 5] |
| `--limit <limit>` | Maximum candidates to print (default 25) [default: 25] |
| `--type <value-type>` | Value type to scan: u32 (default), u64, f32, f64 [default: u32] |

How it works:

- **Heaps.** The unnamed `rw` regions (no path) at or above `--heap-min`,
  largest first; at most 8 of them, and at most `--bytes` from the start of
  each. `--heap-min` takes `0x` hex or decimal, like every other number.
  Unlike [`hot`](#hot), named `[anon:...]` mappings are not included.
- **Timing.** Each heap is read, then `hunt` sleeps `--interval` seconds and
  reads it again, so the whole run waits up to 8 × `--interval` seconds
  (40 s with the default).
- **Matching.** Slots are read little-endian at the type's natural alignment
  and compared as unsigned integers. For `f32`/`f64` that means `<min>` and
  `<max>` are compared against the raw IEEE bit pattern, not the float value.
- **Score.** Higher is better: a value that occurs once in the dump, has no
  other in-range value nearby, a pointer-like 8-byte value in
  `0x7200_0000_0000..0x7300_0000_0000` nearby, or is
  below 10,000,000 scores up. "Nearby" means every 8th byte within 64 bytes
  of the slot (same 8-byte phase as the slot): for `u32` the neighbours 4
  bytes away are not checked, and a slot at an offset ≡ 4 mod 8 only sees
  misaligned pointer reads. Repeated values in table-like neighbourhoods
  score down. `--context` shows 32 bytes starting 8 bytes before the slot.

A read error on any heap aborts the run. If nothing matches, `hunt` prints a
hint (`--heap-min`, `--bytes`, a wider range) and exits 0; `<min>` greater
than `<max>` is an error (exit 1). `hunt` only narrows the field: confirm a
candidate by changing the value in the game and diffing (`dump` +
[`dumpdiff`](#dumpdiff)) or with `search --continue`.

```bash
spectre hunt 4321 259000 259999 --adb
spectre hunt 4321 9000 13000 --adb --heap-min 0x720000000000 --interval 10 --limit 50
spectre hunt 41820 31300 31400 --interval 1 --limit 5 --context
```

Example output (the [practice target](../examples/README.md) on Windows,
native backend; context bytes shortened with `...`):

```
5 candidate(s) of 42 stable values (top by structure score):
ADDRESS                     VALUE  REGION
0x251ad51e5a8               31320  0x251ad4a0000  ctx: 64 41 00 00 00 00 00 00 58 7a 00 00 ...
0x251ad538ab8               31400  0x251ad4a0000  ctx: 4c 66 00 00 00 00 00 00 a8 7a 00 00 ...
0x251ad54a5e8               31368  0x251ad4a0000  ctx: 40 61 00 00 00 00 00 00 88 7a 00 00 ...
0x251ad54aed0               31344  0x251ad4a0000  ctx: b0 16 00 00 00 00 00 00 70 7a 00 00 ...
0x251ad54b868               31384  0x251ad4a0000  ctx: 70 79 00 00 00 00 00 00 98 7a 00 00 ...

next: change the value in-game, re-run `spectre dump` + `dumpdiff`, and check which address moved
```

`REGION` is the start of the heap the candidate was found in. A range this
wide matches many unrelated values (42 here); the next step is always a value
change in the target plus a diff or `search --continue`.

## hot

*Main only.* Search a process's anonymous rw regions for a byte pattern *on
the Android device*. The device runs `dd | od | sed | grep` itself, so only
matching lines cross the adb pipe instead of a full hex dump — a whole-heap
scan takes seconds, which keeps before/after diff cycles short. ADB only.

```
spectre hot [FLAGS] [OPTIONS] <pid> <hex> --adb
```

| Argument | Description |
|----------|-------------|
| `<pid>` | Target process ID |
| `<hex>` | Byte pattern as hex in memory order, e.g. `b8f30300` or `"b8 f3 03 00"` (max 4096 bytes) |

| Flag / option | Description |
|---------------|-------------|
| `--adb` | Use ADB backend (required: the scan runs on the device) |
| `--adb-host <adb-host>` | ADB host (default: 127.0.0.1) |
| `--adb-port <adb-port>` | ADB port (default: 5555) |
| `--base <base>` | Only report matches at or above this address (hex with 0x, or decimal) [default: 0] |
| `--json` | Output as JSON (array of 0x-hex addresses) |
| `--limit <limit>` | Stop after N matches (0 = unlimited) [default: 0] |

Scanned regions are `rw` mappings that are unnamed or `[anon:...]`. Memory is
read in 1 MiB chunks with one page of overlap, so matches across chunk
boundaries are found. On the device, `od -An -tx1 -v -w256` prints 256 bytes
per line as hex text and `grep -bF` returns only the lines that contain the
pattern; spectre then finds every byte-aligned occurrence in those lines
(overlapping ones included). A chunk the device cannot read is skipped with a
warning (a partly readable chunk warns about the short read) instead of
aborting the scan; if nothing at all can be read (no root, dead pid) the
command fails instead of reporting 0 matches. The device needs `su`, `dd`,
`od`, `sed` and `grep` (toybox on Android 8+). Values are not encoded for
you: a little-endian u32 `259000` is `b8f30300`.

Text output is one address per line and a `-- N match(es)` summary line.

> **Limitation.** A match must fit inside one 256-byte `od` line, so an
> occurrence that starts in the last (pattern length − 1) bytes of a line is
> missed (about 1% for a 4-byte pattern), and a pattern longer than 256 bytes
> never matches although up to 4096 bytes are accepted. Re-check a missing
> address with `spectre dump`.

```bash
spectre hot 4321 b8f30300 --adb
spectre hot 4321 "b8 f3 03 00" --adb --base 0x70000000 --limit 50 --json
```

Without `--adb` the command stops before touching any device:

```
error: `spectre hot` greps on the device and needs --adb (use `spectre search` for native)
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

Without `--once`, the bot crate's `TaskScheduler` runs each enabled task on
its own timing: cron `schedule` if set, else `interval_ms`, else
`default_interval_ms`. Task-level `conditions` are checked before each
start; a false condition or an unreadable field skips only that task.
`--once` runs every enabled task once, ignoring the timing but not the
`conditions`. `--dry-run` prints each task's effective timing.

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

## offsets

*Main only.* Show and validate a game's offsets YAML, or list the available
games. There is no `--check` flag: validation always runs when a game is
given.

```
spectre offsets [FLAGS] [game]
```

| Argument | Description |
|----------|-------------|
| `<game>` | Game name (`games/<game>/offsets.yaml`, `games/<game>.yaml` or `.yml`), a name as listed by `spectre offsets`, or a path to an offsets YAML file. Omit to list the available games |

| Flag | Description |
|------|-------------|
| `--json` | Output as JSON (`path`, `offsets`, `issues`) |

With a game, prints every field as a table (structure with base offset,
field, type, offset, description), then a validation report: `ok` or a
list of issues with the structure/field they belong to.

| Check | Severity |
|-------|----------|
| Empty `version` | error |
| Duplicate structure name | error |
| Duplicate field name within a structure | error |
| Unknown field type | error |
| String length 0 (`string:0`, `String(0)`, `length: 0`) | error |
| Overlapping field byte ranges within a structure (`offset` .. `offset + size(type)`) | warning |

Exits with status 1 if any error is found; warnings alone exit 0, since
placeholder offsets may overlap until they are confirmed.

The file is read in the spectre-game format, where `game`, `version` and
each field's `offset` are required: a file missing one of them fails to
parse (exit 1, no report) even though `--offsets` would accept it.

```bash
spectre offsets
spectre offsets afk-journey
spectre offsets examples/practice-offsets.yaml --json
```

Example output (repository checkout, rows shortened with `...`):

```
> spectre offsets
afk-journey

> spectre offsets afk-journey
afk-journey v1.0.45  (games/afk-journey/offsets.yaml)

STRUCTURE                   FIELD          TYPE        OFFSET    DESCRIPTION
PlayerState @ 0x1a2b3c00    player_id      U32         0x0       Account ID (observed 60068087 in profile panel)
PlayerState @ 0x1a2b3c00    level          U32         0x4       Player level
...
Resources @ 0x724df0000000  team_power     I64         0xa578    Team combat power (HUD shows rounded '259K'; raw 259850 stable across restarts).
...

validation: ok
```

## serve

Start the read-only web dashboard (127.0.0.1 only).

```
spectre serve [FLAGS] [OPTIONS]
```

| Flag / option | Description |
|---------------|-------------|
| `-p`, `--port <port>` | Port to listen on; always bound to 127.0.0.1 (0 = pick a free port) [default: 8787] |
| `--rate-limit <n>` | Max `/api/read` + `/api/search` requests per minute and client (at least 1) [default: 60] |
| `--allow-origin <origin>` | Extra origin allowed to call the API via CORS, e.g. `https://tool.example` (repeatable; no wildcards) [default: same-origin only] |
| `--adb` | Use ADB backend instead of native |
| `--adb-host <adb-host>` | ADB host (default: localhost) |
| `--adb-port <adb-port>` | ADB port (default: 5555) |

Prints the dashboard URL (`http://127.0.0.1:<port>/`) and serves until
Ctrl+C. The server only binds the loopback interface, and there is
deliberately no `--host` option: the dashboard shows process memory without
any authentication, so it must never listen on a network interface. For
remote use, tunnel it instead (`ssh -L 8787:127.0.0.1:8787 <host>`). The
browser UI is embedded in the binary (no CDN, works offline) and
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
unknown pid, ADB offline) HTTP 502 with a generic message such as
`read failed` (never paths or environment values). Hardening:

- Requests whose `Host` is not `127.0.0.1:<port>` / `localhost:<port>`, or
  that come from another website (`Origin` / `Sec-Fetch-Site`), are refused
  with HTTP 403 (DNS-rebinding protection).
- CORS is off by default; `--allow-origin` adds origins that may call the
  API cross-origin. `Access-Control-Allow-Origin` echoes the listed origin,
  never `*`.
- `/api/read` and `/api/search` share a per-client budget of `--rate-limit`
  requests per minute (HTTP 429 with `Retry-After` beyond it); at most two
  searches run at once (HTTP 429 otherwise).
- Every response carries `Content-Security-Policy`,
  `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`.

See `spectre-web/README.md` for details.

```bash
spectre serve                 # http://127.0.0.1:8787/
spectre serve --port 0        # pick a free port, print it
spectre serve --adb           # inspect an Android emulator via ADB
spectre serve --rate-limit 120 --allow-origin http://localhost:3000
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

```
spectre adb list
spectre adb ping [serial]
```

| Argument | Description |
|----------|-------------|
| `<serial>` | ADB device serial number (`ping` only) |

**`list`** runs `adb devices -l` and prints a `DEVICE` / `STATE` / `MODEL`
table followed by `found N device(s)`. If no device is listed, it prints
`no ADB devices found` and (*main only*) falls back to BlueStacks NXT
discovery: it reads every `bst.instance.<name>.adb_port` entry from
`%PROGRAMDATA%\BlueStacks_nxt\bluestacks.conf`, runs
`adb connect 127.0.0.1:<port>` for each, and lists the instances that report
`device` with `BlueStacks` as the model. Instances that are not running are
skipped with a warning. The printed serial `127.0.0.1:<port>` is the host
and port to pass as `--adb-host` / `--adb-port` (`scan`, `hunt`, `hot`,
`serve`); commands with only `--adb` (`dump`, `search`, `find`, ...) always
use `127.0.0.1:5555`.

**`ping`** runs `adb [-s <serial>] get-state` and prints the state, the
round-trip latency in milliseconds and `OK` (state `device`) or
`UNKNOWN/OFFLINE`. If `adb get-state` fails (no device, unknown serial), it
prints adb's error and exits with 1.

**adb binary** (*main only*). Both subcommands, and the `--adb` backend of
every other command, use `adb` from `PATH` if it is there, otherwise the
first existing one of `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`,
`C:\Program Files\BlueStacks_nxt\HD-Adb.exe`,
`%PROGRAMDATA%\BlueStacks_nxt\HD-Adb.exe` and `adb.exe` in the current
folder. v0.3.0 only uses `adb` from `PATH`.

```bash
spectre adb list
spectre adb ping
spectre adb ping 127.0.0.1:5555
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

**Rounded or unknown value (main only).** When the game only shows "259K",
start with a range instead of an exact value: [`search --min/--max`](#search)
over all memory, or [`hunt`](#hunt) for values that stay stable over a few
seconds. Once you know an exact value, [`hot`](#hot) finds its bytes on an
Android device in seconds, which keeps each before/after round short.

```bash
spectre search 4321 u32 --min 259000 --max 259999 --adb
spectre hunt 4321 259000 259999 --adb
# ...change the value in the game, read the exact new value...
spectre hot 4321 b8f30300 --adb        # exact value as LE bytes (u32 259000)
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
conditions checked before each task start (see [`bot`](#bot)).

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
