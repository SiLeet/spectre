# spectre-mcp

stdio MCP server (JSON-RPC 2.0, one message per line) that gives agents the
live memory pipeline as typed tools. It wraps `spectre.exe` and `adb`; stdout
carries only protocol messages, logs go to stderr. Tool errors come back as
`isError` results with a German hint on what to do next (e.g. "kein Device:
scripts/bluestacks-ensure.sh starten").

> **The server serializes everything.** It is the only adb owner: every
> external command runs under one mutex, and after every spectre command it
> runs `adb connect <SERIAL>` (spectre may restart the adb server). Never run
> the spectre CLI or adb in parallel while an agent uses this server.

## Tools

| Tool | Arguments | Runs |
|------|-----------|------|
| `health` | – | `tasklist` (HD-Player.exe), `adb connect`, `adb get-state` → `{bluestacks_running, adb_state, hint}` |
| `find` | `process` | `spectre find <process> --adb --json` → `{pid, processes}` |
| `regions` | `pid`, `rw_only` (true), `min_size_bytes` (0) | `spectre regions <pid> --adb --json [--filter rw]`, filtered by size |
| `dump` | `pid`, `addr`, `size`, `out` | `spectre dump ... --adb --format raw --output <out>` → `{path, size, sha1}` |
| `dumpdiff` | `a`, `b`, `base` (0) | `spectre dumpdiff <a> <b> --base <base> --json` |
| `read` | `pid`, `addr`, `type` (u8/u16/u32/u64/i32/f32/f64) | small temp dump, parsed little-endian → `{value}` |
| `hot` | `pid`, `hex`, `base?`, `limit?` | `spectre hot ... --adb --adb-host/--adb-port --json` |
| `hunt` | `pid`, `min`, `max`, `type` (u32) | `spectre hunt ... --adb --adb-host/--adb-port --type` |
| `search` | `pid`, `type`, `value` or `min`+`max`; optional `continue` (refine the previous hits), `state` | `spectre search ... [--continue] [--state PATH] --adb` |
| `chain` | `pid`, `base`, `offsets?` | `spectre chain <base> --pid <pid> --adb --json [--offsets]` |
| `offsets` | `game?` | `spectre offsets [game] --json` |
| `adb_tap` | `x`, `y` | `adb -s <SERIAL> shell input tap x y` |
| `adb_key` | `name` (back, home, KEYCODE_ENTER, 4) | `adb -s <SERIAL> shell input keyevent KEYCODE_...` |
| `adb_screencap` | `out_png` | `adb -s <SERIAL> exec-out screencap -p` → file |

`dump`, `find`, `regions`, `search` and `chain` only have `--adb` in the CLI
and always use 127.0.0.1:5555; `hot` and `hunt` get the host/port from `SERIAL`.

## Configuration (environment)

| Variable | Default |
|----------|---------|
| `SPECTRE_BIN` | `target/release/spectre.exe` (relative to the working directory) |
| `ADB_BIN` | `%LOCALAPPDATA%/Android/Sdk/platform-tools/adb.exe` (`adb` if unset) |
| `SERIAL` | `127.0.0.1:5555` |
| `CMD_TIMEOUT_SECONDS` | `120` (per external command; the process is killed after it) |

## `.mcp.json`

```json
{
  "mcpServers": {
    "spectre": {
      "command": "C:/Users/Sigi/spectre/target/release/spectre-mcp.exe",
      "env": {
        "SPECTRE_BIN": "C:/Users/Sigi/spectre/target/release/spectre.exe",
        "SERIAL": "127.0.0.1:5555"
      }
    }
  }
}
```

Build: `cargo +stable-x86_64-pc-windows-gnu build --release -p spectre-mcp -p spectre-cli`.
