# 10-minute quickstart

From zero to a working memory scan in about ten minutes. You do not need a
game for the first part: a tiny practice program plays the role of the game,
and you find its "score" in memory the same way you would find gold or HP in
a real one.

| Step | What you do | Needs |
|------|-------------|-------|
| [0](#step-0--get-spectre) | Get the `spectre` binary | download, or Rust to build |
| [1](#step-1--practice-without-a-game) | Find a changing value in a practice process | PowerShell or Python |
| [2](#step-2--the-same-on-a-real-game-afk-journey) | Same workflow on AFK Journey | the game |
| [3](#step-3--validate-a-bot-config) | Validate a bot config | nothing |
| [4](#step-4--lua-scripts) | Run Lua scripts | practice target (game + adb for `afk-bot.lua`) |

All output below is real output from spectre 0.2.0 on Windows 11, shortened
where marked with `...`. Your PIDs, addresses and hit counts will differ.

## Files in this folder

| File | What it is |
|------|------------|
| `practice-target.ps1` | Practice "game" for PowerShell: prints its PID and a score, Enter adds 100 |
| `practice_target.py` | The same in Python |
| `practice-offsets.yaml` | Offsets file describing the practice target's memory layout |
| `practice.lua` | Lua script that watches the practice score (reads only, no adb) |
| `bot-config.yaml` | Demo bot config for AFK Journey (three tasks, one cron-scheduled) |
| `afk-bot.lua` | Demo Lua bot for AFK Journey (needs the game and adb) |

---

## Step 0 — get spectre

Pick one:

**(a) Download a release.** From
<https://github.com/SiLeet/spectre/releases/latest> take either

- `spectre-v0.2.0-windows-x64.exe` — a single file, no runtime needed, or
- `spectre-v0.2.0-x86_64-pc-windows-msvc.zip` /
  `spectre-v0.2.0-x86_64-unknown-linux-gnu.tar.gz` — binary plus `games/`,
  `examples/`, README and LICENSE.

Run spectre from a folder that contains `games/` (the unpacked zip/tar.gz has
it), otherwise game offset files are not found. The examples below call it
`spectre`; with the single `.exe`, rename it to `spectre.exe` or type the full
file name.

**(b) Build from source.** You need Rust (<https://rustup.rs>) and, on
Windows, the Visual Studio C++ Build Tools.

```powershell
git clone https://github.com/SiLeet/spectre.git
cd spectre
cargo build -r
# binary: target\release\spectre.exe (Linux: target/release/spectre)
$env:Path = "$PWD\target\release;$env:Path"   # PowerShell, this window only
```

Check it works:

```
> spectre info
spectre-cli v0.2.0
  ...
Backends:
  native           — NativeWindows
  adb              — missing (adb not on PATH)

Installed Games:
  - afk-journey
```

`adb` is only needed for Android emulators and for bot clicks; everything in
step 1 works without it. Run all following commands from the repository (or
unpacked release) folder.

---

## Step 1 — practice without a game

The practice target keeps a 32-bit score at a fixed place in its own memory
and adds 100 every time you press Enter. It touches nothing but itself.

> **Why a special script?** PowerShell and Python normally store numbers as
> runtime objects that get a *new* address every time the value changes, so
> `search --continue` would lose them. The practice targets keep the score in
> a plain 4-byte buffer (`Marshal.AllocHGlobal` / `ctypes`) that stays put —
> just like a field in a game's player struct.

**Window A** — start the target and leave it open:

```
> powershell -ExecutionPolicy Bypass -File examples\practice-target.ps1
spectre practice target
PID:   38300
score: 31337
Press Enter to add 100 to the score, q + Enter to quit.
```

(Python instead: `python examples/practice_target.py`. Both accept
`-Reveal` / `--reveal` to print the score's address as an answer key.)

**Window B** — hunt for the score.

1. Find the process. The target prints its own PID, but this is how you would
   get it for a game:

   ```
   > spectre find powershell
   PID       NAME
   31088     powershell.exe
   36600     powershell.exe
   28776     powershell.exe
   38300     powershell.exe
   found 4 process(es)
   ```

2. Search all readable memory for the current score:

   ```
   > spectre search 38300 u32 31337
   0x01e4805f8ee8
   0x01e4806384f0
   ...
   0x01e480906470
   0x01e4f03d31c0
   -- 12 result(s), saved to .spectre-search.json
   ```

   Twelve places happen to hold 31337. The candidates are saved to
   `.spectre-search.json` in the current folder.

3. Change the value: press **Enter in window A** (`score: 31437`).

4. Keep only the candidates that now hold the new value. Pass the PID again —
   `--continue` needs it:

   ```
   > spectre search 38300 u32 31437 --continue
   0x01e4f03d31c0
   -- 1 result(s), saved to .spectre-search.json
   ```

   One address left: that is the score. (With a real game, repeat
   change + `--continue` until one or a few addresses remain.)

5. Look at the bytes there. `0x7acd` = 31437, little-endian; the next byte
   counts the Enter presses:

   ```
   > spectre dump 38300 0x01e4f03d31c0 32
   000001e4f03d31c0  cd 7a 00 00 01 ab ab ab ab ab ab ab ab ab ab ab   .z..............
   000001e4f03d31d0  ab ab ab ab ab ab ab ab ab ab ab ab ab ab ab ab   ................
   ```

6. Save that range as a raw dump, change the value, save again:

   ```
   > spectre dump 38300 0x01e4f03d31c0 32 --format raw --output before.dump
   wrote 32 bytes to before.dump
   ```

   Press **Enter in window A** (`score: 31537`), then:

   ```
   > spectre dump 38300 0x01e4f03d31c0 32 --format raw --output after.dump
   wrote 32 bytes to after.dump
   ```

7. Compare the two dumps. `--base` makes the printed offsets real addresses:

   ```
   > spectre dumpdiff before.dump after.dump --base 0x01e4f03d31c0
   1 changed region(s), 3 changed byte(s)  (old: 32 bytes, new: 32 bytes)
   0x1E4F03D31C0  old: cd 7a 00 00 01  new: 31 7b 00 00 02
   ```

   This is the "I don't know the value, only that it changed" technique: dump
   a bigger range before and after an action in the game, and `dumpdiff`
   shows what moved.

8. Optional — read the dump through an offsets file.
   `practice-offsets.yaml` describes the layout (score `u32` at 0, round
   counter `u8` at 4); `scan --dump` works offline, no process needed:

   ```
   > spectre scan practice --offsets examples/practice-offsets.yaml --dump after.dump --dump-base 0x01e4f03d31c0

   Pattern: PracticeScore
   Matches: 1
   --------------------------------------------------------------------------------
     Address: 0x1e4f03d31c0
       [0x0000] score                = 31 7b 00 00
       [0x0004] round                = 02
       [0x0005] marker               = ab ab ab ab ab ab ab ab ab ab ab
   ```

   `scan` matches the structure's *layout*, not its values, so on a large dump
   or a live process it reports many positions. It shines once you have real
   offsets for a game.

Quit the target with `q` + Enter (or close window A). `before.dump` /
`after.dump` are git-ignored; delete `.spectre-search.json` when you are done.

---

## Step 2 — the same on a real game (AFK Journey)

Same commands, a real process. Start the game, then:

```powershell
spectre find afk                          # note the PID, e.g. 12345
spectre search 12345 u32 1520             # your current gold, as shown in game
# ...spend or earn gold...
spectre search 12345 u32 1480 --continue  # repeat until few addresses remain
spectre dump 12345 0x1a2b3c00 4096 --format raw --output before.dump
# ...do something in the game...
spectre dump 12345 0x1a2b3c00 4096 --format raw --output after.dump
spectre dumpdiff before.dump after.dump --base 0x1a2b3c00
```

Things to know:

- Games often store a value in several places (display copy, server copy);
  narrow down until the remaining addresses all change together.
- Games protected by anti-cheat may refuse memory reads; reading another
  user's or an elevated process needs an elevated shell. On Linux, reading
  `/proc/<pid>/mem` of a process that is not your child usually needs `sudo`.
- Addresses of heap values change on every game start. To make a find
  reusable, express it relative to a stable base and put it into
  `games/<game>/offsets.yaml` — see
  [docs/game-integration.md](../docs/game-integration.md).
- `spectre scan afk-journey [--pid N | --dump FILE]` uses
  `games/afk-journey/offsets.yaml`. That file contains **placeholder**
  offsets, and in 0.2.0 `scan` cannot load it at all (`missing field 'type'`:
  the file uses `field_type: U32`, `scan` reads `type: u32`). Until that is
  fixed, pass your own file with `--offsets`, written like
  `practice-offsets.yaml`.
- For an Android emulator add `--adb` to `find`, `search`, `dump` and
  `regions` (needs `adb` on PATH and a connected device, see `spectre adb list`).

---

## Step 3 — validate a bot config

`bot-config.yaml` drives the AFK Journey demo with three tasks. The third,
`periodic-claim`, uses a cron `schedule: "0 */6 * * *"` (every six hours)
instead of `interval_ms`. `--dry-run` parses and validates the file without
touching any process:

```
> spectre bot examples/bot-config.yaml --dry-run
config validated successfully:
  instance:         default
  input backend:    adb
  default interval: 5000 ms
  memory poll:      250 ms
  enabled:          true
  tasks:            3
    - health-watch (interval=2000 ms, enabled=true, actions=2)
    - collect-rewards (interval=15000 ms, enabled=true, actions=4)
    - periodic-claim (interval=0 ms, enabled=true, actions=2)
```

A malformed `schedule` is rejected here; a valid one is not printed (the
cron task shows `interval=0 ms`).

Running it for real (`spectre bot examples/bot-config.yaml --once`) needs the
game process from `metadata.process`; without it spectre stops with
`cannot resolve bot target pid: set metadata.pid or metadata.process in the bot config`.
Note that the CLI loop runs **every enabled task's actions each round and
then sleeps `default_interval_ms`** — per-task `interval_ms`, task-level
`conditions` and `schedule` are validated but not applied yet. Guard steps
with `!MemoryCheck` / `!Condition` actions instead.

---

## Step 4 — Lua scripts

**Practice script (works now).** With the practice target from step 1 still
running, point `practice.lua` at the PID and address you found. It reads the
score ten times, one second apart; press Enter in window A meanwhile:

```
> $env:SPECTRE_PID  = "38300"
> $env:SPECTRE_ADDR = "0x01e4f03d31c0"
> spectre script examples/practice.lua
[lua] watching pid 38300, address 0x1e4f03d31c0
[lua] read  1: score = 31537  (changed)
[lua] read  2: score = 31537
...
[lua] read  5: score = 31637  (changed)
...
[lua] read 10: score = 31637
[lua] done - press Enter in the practice target while this runs to see the value change
```

(bash: `SPECTRE_PID=38300 SPECTRE_ADDR=0x01e4f03d31c0 spectre script examples/practice.lua`)

**AFK Journey bot.** `afk-bot.lua` is the real-game demo. It first waits for
`afk_journey.exe`, then reads placeholder offsets and taps buttons through
adb. Without the game it simply waits until you press Ctrl+C:

```
> spectre script examples/afk-bot.lua
[lua] === AFK Journey Bot Starting ===
[lua] Waiting for afk_journey.exe ...
[lua] Waiting for afk_journey.exe ...
```

To run it for real you need the game, real offsets in place of the
`0x12345678` placeholders, and `adb` with a connected device for the clicks
(`--input-backend adb` is the default).

Scripts get two modules: `spectre` (`read_u32`, `read_u64`, `read_i32`,
`read_f32`, `read_string`, `read_fields`, `regions`, `find_process`, `scan`)
and `bot` (`click`, `swipe`, `wait`, `log`).

---

## Known limitations (0.2.0)

- `search --json` is accepted but does nothing: output is always one address
  per line plus a summary line.
- `search --continue` needs the `<pid>` although `--help` says it can be
  omitted — without it the command fails with a usage error.
- `search` values are unsigned: negative numbers (`i32 -5`) are rejected.
  Search for the two's-complement value instead (`u32 4294967291`).
- `search --limit N` stops the *first* scan after N hits, so the address you
  want may not be among them; leave it off while hunting.
- `spectre bot` ignores per-task `interval_ms`, `conditions` and `schedule`
  (see step 3).
- `spectre scan afk-journey` cannot load the bundled placeholder offsets
  (see step 2); `scan` also never reports a structure that reaches into the
  last *structure-size* bytes of a memory region or dump (a 16-byte dump of
  a 16-byte structure gives `Matches: 0`).

## Next steps

- [docs/getting-started.md](../docs/getting-started.md) — installation and
  ADB setup in more detail
- [docs/cli-reference.md](../docs/cli-reference.md) — every command and flag
- [docs/game-integration.md](../docs/game-integration.md) — write an offsets
  file for a new game
