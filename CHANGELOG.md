# Changelog

## 0.4.0 (2026-10-31)

### Features

- **[`spectre hunt`](#spectre-hunt)** — finds offset candidates by diffing dumps for value ranges (3e742dd)
- **[`spectre hot`](#spectre-hot)** — scans on the device (`od` + `grep`) and sends only the hits over adb (636e312, T13; fixes f3adde9, b56f897, 97b32ee)
- **[`spectre offsets`](#spectre-offsets)** — YAML offset viewer and validator (15449e7, T15)
- **[`spectre search --min/--max`](#spectre-search---min--max)** — range search, including f32 (9a35b3c, T14)
- **[`spectre adb list/ping`](#spectre-adb-listping)** — auto-discovers the adb binary and BlueStacks instances (b809cb1)

### Improvements

- bot: ADB memory backend for `spectre bot` + verified AFK Journey live bot config (examples/bot-config-afk-live.yaml) (b60401f)
- bot: `spectre bot` honours per-task `schedule` > `interval_ms` > default and head `conditions`; Ctrl+C stops promptly, tick-loop panics exit non-zero (43999b2, 08f8c78, T19)
- adb: live Android support (root fallback, Android `ps` format, serial pinning) (7f8c258)
- adb: page-aware 4K reads, 7x faster dumps (6a36d58)
- native: Linux reader via `/proc/<pid>/mem` pread (30b197a, T17)
- examples: AFK Journey safe-action bot templates (9065aa7, T16)
- game(afk-journey): measured offsets, team power vs. gold corrected, team_power verified live via `spectre hot` (db5452f, d97e1cf, e0e9d03)
- docs: CLI reference and README cover hunt, hot, offsets, range search and adb discovery (8a7deee, cca8021, 6c0e59f, T20)

### Feature reference

#### spectre hunt
Takes memory dumps between value changes and narrows down candidate offsets.

#### spectre hot
Runs the scan on the device itself, so only matching offsets come back over adb.

#### spectre offsets
Shows a game's YAML offsets and checks them for errors.

#### spectre search --min/--max
Matches values in a range instead of one exact value. Also works for f32.

#### spectre adb list/ping
The subcommands existed before. `list` and `ping` now find adb and BlueStacks instances on their own.

## 0.3.0

See tag `v0.3.0`.
