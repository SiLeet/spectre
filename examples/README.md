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
| [5](#step-5--afk-journey-pattern-from-placeholder-to-real-offset) | Turn a placeholder offset into a real one | the game |

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
| `afk-bot.lua` | Demo Lua bot for AFK Journey, modes `battle` and `safe_claim` (needs the game and adb) |
| `bot-config-afk.yaml` | AFK Journey bot with only safe actions (claim rewards, idle check, Homestead) — placeholders |
| `afk-offsets-placeholder.yaml` | Placeholder gold/EXP addresses (`0xDEADBEEF`, `0xCAFEBABE`) for `bot-config-afk.yaml` |

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

> **Practice files are not in the 0.2.0 packages.** The v0.2.0 zip/tar.gz
> only has `afk-bot.lua` and `bot-config.yaml` in `examples/`, and the single
> `.exe` has no `examples/` at all. The practice files arrive with the next
> release. Until then, get them from the repository: clone it (see (b)), or
> download them into an `examples\` folder next to spectre:
>
> ```powershell
> New-Item -ItemType Directory -Force examples | Out-Null
> foreach ($f in 'practice-target.ps1','practice_target.py','practice-offsets.yaml','practice.lua') {
>   Invoke-WebRequest "https://raw.githubusercontent.com/SiLeet/spectre/main/examples/$f" -OutFile "examples\$f"
> }
> ```

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
step 1 works without it. Run all following commands from the folder that
contains `examples/` with the practice files: the cloned repository, or the
release folder you downloaded them into.

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

8. Optional — read a dump through an offsets file.
   `practice-offsets.yaml` describes the 16-byte layout (score `u32` at 0,
   round counter `u8` at 4, 11 marker bytes); `scan --dump` works offline, no
   process needed. Dump exactly those 16 bytes:

   ```
   > spectre dump 38300 0x01e4f03d31c0 16 --format raw --output score.dump
   wrote 16 bytes to score.dump
   > spectre scan practice --offsets examples/practice-offsets.yaml --dump score.dump --dump-base 0x01e4f03d31c0

   Pattern: PracticeScore
   Matches: 1
   --------------------------------------------------------------------------------
     Address: 0x1e4f03d31c0
       [0x0000] score                = 31 7b 00 00
       [0x0004] round                = 02
       [0x0005] marker               = ab ab ab ab ab ab ab ab ab ab ab
   ```

   `scan` matches the structure's *layout*, not its values: it tests every
   4-byte-aligned position where the whole structure fits, including one
   that ends exactly at the end of the dump. On the 32-byte `after.dump` it
   therefore reports 5 positions (the score address and the next four), and
   on a large dump or a live process many more. It shines once you have real
   offsets for a game.

   > **0.2.0 release binary:** its `scan` skips the last *structure-size*
   > bytes of a dump, so it reports `Matches: 0` for `score.dump`; scan the
   > 32-byte `after.dump` there instead (one match, at the score address).
   > Builds from the current source do not have this bug.

Quit the target with `q` + Enter (or close window A). The `.dump` files are
git-ignored; delete `.spectre-search.json` when you are done.

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
  offsets, so its matches are layout hits, not your gold. Pass your own file
  with `--offsets`, written like `practice-offsets.yaml` (`type: u32` and
  `field_type: U32` both work, see
  [docs/game-integration.md](../docs/game-integration.md#field-types)). The
  0.2.0 release binary cannot load the bundled file at all
  (`missing field 'type'`); builds from the current source can.
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
    - health-watch (interval=2000 ms, enabled=true, conditions=1, actions=2)
    - collect-rewards (interval=15000 ms, enabled=true, conditions=0, actions=4)
    - periodic-claim (schedule="0 */6 * * *", enabled=true, conditions=0, actions=2)
```

A malformed `schedule` is rejected here. Each task line shows the timing the
bot really uses: the `schedule`, or the interval (`(default)` when the task
has no `interval_ms` and falls back to `default_interval_ms`).

Running it for real (`spectre bot examples/bot-config.yaml --once`) needs the
game process from `metadata.process`; without it spectre stops with
`cannot resolve bot target pid: set metadata.pid or metadata.process in the bot config`.
Without `--once` each task runs on its own timing: `schedule` if set (at most
once per matching minute), else `interval_ms`, else `default_interval_ms`.
Task-level `conditions` are checked before each start; a false condition or
an unreadable field skips only that task (`-vv` shows the skip reasons).
`--once` runs every enabled task one time right away, ignoring the timing but
not the `conditions`. Inside a task, guard steps with `!Condition` actions: a
failed `!MemoryCheck` only prints a warning, the actions after it still run.

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

`afk-bot.lua` has a second mode, `safe_claim`, that only reads gold/EXP and
claims login rewards every five minutes, logging gold before and after the
claim. Select it with `$env:SPECTRE_MODE = "safe_claim"` (bash:
`SPECTRE_MODE=safe_claim`). Its `OFFSET_GOLD = 0xDEADBEEF` and
`OFFSET_EXP = 0xCAFEBABE` are placeholders: until you replace them it logs
`read at 0xDEADBEEF failed` and does not click.

Scripts get two modules: `spectre` (`read_u32`, `read_u64`, `read_i32`,
`read_f32`, `read_string`, `read_fields`, `regions`, `find_process`, `scan`)
and `bot` (`click`, `swipe`, `wait`, `log`).

---

## Step 5 — AFK Journey pattern: from placeholder to real offset

`bot-config-afk.yaml` and the `safe_claim` mode of `afk-bot.lua` use only the
zero-risk actions from [docs/afk-journey-guide.md](../docs/afk-journey-guide.md#trigger-actions-for-offset-confirmation-cheap--safe):
claim login rewards, read gold/EXP, Homestead visitor requests. They ship
with placeholder addresses. Check the file first:

```
> spectre bot examples/bot-config-afk.yaml --dry-run
config validated successfully:
  instance:         default
  input backend:    adb
  default interval: 300000 ms
  memory poll:      250 ms
  enabled:          true
  tasks:            3
    - claim_rewards (interval=300000 ms (default), enabled=true, conditions=0, actions=1)
    - idle_check (schedule="*/5 * * * *", enabled=true, conditions=0, actions=3)
    - homestead_request (interval=300000 ms (default), enabled=false, conditions=0, actions=6)
```

`homestead_request` is disabled on purpose: bundle (real-money) popups can
appear on Homestead entry and its tap positions are not in the guide.
`claim_rewards` runs at start and then every `default_interval_ms` = 5
minutes; `idle_check` runs at :00, :05, :10, ... (its `schedule`).

To replace a placeholder — here gold, shown in the Town screen top-left:

1. **Note the value and find the process.** The game rounds: "259K" means
   somewhere between 259000 and 259999.

   ```powershell
   spectre find afk                     # note the PID, e.g. 12345
   ```

2. **Hunt the range.** `hunt` dumps the busiest heaps twice, 5 s apart, and
   keeps values inside the range that did not change. Do not touch the game
   meanwhile.

   > **Not in the 0.2.0 or 0.3.0 release binaries:** `hunt` is only in a
   > build from source of the current `main` (step 0 (b)). With a release
   > binary, narrow the value down with `search` as in step 2 instead.

   ```powershell
   spectre hunt 12345 259000 259999 --context
   spectre hunt 12345 259000 259999 --type u64 --context   # if gold is 8 bytes
   ```

   Note the top few candidate addresses.

3. **Confirm with a safe action and `dumpdiff`.** Dump a range around a
   candidate, do a safe action that gives gold, dump again. Check first that
   it really gives gold: the Journey's Gift reward can be diamonds only, or
   nothing ("Tomorrow"); the AFK Treasure Chest in Homestead gives gold.

   ```powershell
   spectre dump 12345 0x1a2b3c00 4096 --format raw --output before.dump
   # ...claim Journey's Gift (if it has gold) or the AFK Treasure Chest...
   spectre dump 12345 0x1a2b3c00 4096 --format raw --output after.dump
   spectre dumpdiff before.dump after.dump --base 0x1a2b3c00
   ```

   The address whose bytes grew by the claimed amount is gold. A value that
   moved by something else is a copy or unrelated; one that did not move
   only rules itself out if the action really gave gold.

4. **Put it into the offsets file.** In `examples/afk-offsets-placeholder.yaml`
   replace `base_offset: 0xDEADBEEF` with the address (the bot reads
   `base_offset + offset`, and `offset` is `0`). Same for EXP and
   `0xCAFEBABE`. For the Lua bot set `OFFSET_GOLD` / `OFFSET_EXP` in
   `afk-bot.lua`. Fix the `type:` if `hunt` found it as `u32` instead of
   `i64`/`u64`.

5. **Verify.** One round, with logs:

   ```powershell
   spectre -v bot examples/bot-config-afk.yaml --once
   ```

   `memory check 'gold' passed` instead of
   `ReadProcessMemory at 0xdeadbeef failed` means the address is readable;
   the `safe_claim` Lua mode also prints the gold before and after the claim.

Things to know:

- Heap addresses change on every game start: after a restart, repeat steps
  2-4, or follow a pointer chain to a stable base
  (`spectre chain`, [docs/game-integration.md](../docs/game-integration.md)).
- `spectre bot` and `spectre script` read memory **natively** only. An
  address found with `hunt/search/dump --adb` inside an Android emulator
  cannot be read by them; only the CLI commands with `--adb` can.
- Lines marked `REPLACE` in the YAML/Lua are coordinates or addresses that
  are not verified (coordinates are for BlueStacks 1920x1080).

---

## Live bot: AFK Journey (verified 2026-10-31)

`bot-config-afk-live.yaml` claims the AFK idle chest (gold + EXP + essence) on a
real BlueStacks instance, guarded by a live memory read of `team_power`.

```bash
# 1. find the game pid (changes on every app restart)
spectre find igame --adb
# 2. find the hot-heap base (ASLR — see the big 0x72... rw- anon region)
spectre regions <pid> --adb
# 3. put pid + heap_base into metadata, then validate and probe
spectre bot examples/bot-config-afk-live.yaml --dry-run
spectre -v bot examples/bot-config-afk-live.yaml --adb --once
# 4. run the loop (claims every 15 min)
spectre -v bot examples/bot-config-afk-live.yaml --adb
```

Verification: the AFK timer resets (`05:38:40` -> `00:00:02`; a `--once` run
started from the hero-detail panel read `00:02:06` exactly two minutes later).

Requirements / pitfalls:

- Only one adb device entry, or the taps fail with `more than one
  device/emulator`. The CLI resolves the serial itself since `f828677`; if taps
  fail, check `adb devices` for a duplicate TCP entry.
- The tap sequence prepends two back-taps + an empty-ground tap so it starts
  from the world view regardless of which panel was open. Without that reset,
  runs silently no-op (three runs left the timer untouched).
- `gold` is NOT wired: the offset is still unpinned (see TODOS.md). The AFK
  pool offsets from 0.3.0 are stale — the heap layout moves between restarts.

## Known limitations (0.4.0)

- `search --json` is accepted but does nothing: output is always one address
  per line plus a summary line.
- `search --continue` needs the `<pid>` although `--help` says it can be
  omitted — without it the command fails with a usage error.
- `search` values are unsigned: negative numbers (`i32 -5`) are rejected.
  Search for the two's-complement value instead (`u32 4294967291`).
- `search --limit N` stops the *first* scan after N hits, so the address you
  want may not be among them; leave it off while hunting.
- The 0.2.0 and 0.3.0 release binaries of `spectre bot` ignore per-task
  `interval_ms`, `conditions` and `schedule`; newer builds apply them (see
  step 3).
- `spectre bot` and `spectre script` have no `--adb` memory reader (see
  step 5).

## Next steps

- [docs/getting-started.md](../docs/getting-started.md) — installation and
  ADB setup in more detail
- [docs/cli-reference.md](../docs/cli-reference.md) — every command and flag
- [docs/game-integration.md](../docs/game-integration.md) — write an offsets
  file for a new game
