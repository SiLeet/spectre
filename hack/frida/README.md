# Frida kit — Unity timeScale probe / setter (T63, Wave-3 H2)

Risk class **L3** (Safety-Matrix, `docs/claude-wave-3-plan.md` §2): client-only,
in-memory, gone after an app restart. Order is always **probe (log-only) →
measure → set**. Attach **after** the game has logged in.

| File | Does |
|---|---|
| `attach.py` | wraps `frida` / `frida-ps` for the BlueStacks adb device; finds the game by `igame` (same key as `spectre find igame`); `--dry-run` prints the command |
| `probe_timescale.js` | **read-only**: logs `Time.timeScale`, `fixedDeltaTime`, `Application.targetFrameRate`, `QualitySettings.vSyncCount` and every `set_timeScale` call |
| `set_timescale.js` | sets `Time.timeScale` to the `scale` parameter (clamped to (0, 4]); optional `repeat_ms` re-applies it when the game resets it |

frida-tools is the only extra dependency (kit only — the repo tests do not
need it). On this host (2026-11-03) it is **not installed** yet.

## Setup on this host (Windows, BlueStacks 5 instance `Pie64`, adb `127.0.0.1:5555`)

Everything below touches the device → **Hermes / live lane only**, while the
bot is idle (the spectre-mcp server owns adb; never `adb kill-server`).

```bash
ADB="$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe"
```

1. **Tools on the PC** — frida-tools pins a frida version; the server must match it exactly:
   ```bash
   python -m pip install frida-tools
   frida --version        # e.g. 17.x.y -> download frida-server 17.x.y
   ```
2. **Device ABI** — pick the matching server build (`frida-server-<ver>-android-<abi>.xz`
   from https://github.com/frida/frida/releases):
   ```bash
   "$ADB" -s 127.0.0.1:5555 shell getprop ro.product.cpu.abilist
   ```
   BlueStacks Pie64 normally reports `x86_64,...,arm64-v8a` (x86 Android with an ARM
   translation layer). **LIVE to check:** if AFK Journey's `libil2cpp.so` is ARM code
   running under `libhoudini`/`libndk_translation`, an x86_64 frida-server cannot see it —
   `probe_timescale.js` prints exactly that. Then the options are an ARM-native image or
   a different hook point; do not force it.
3. **Root** — frida-server needs root. On this host `bluestacks.conf` currently has
   `bst.feature.rooting="0"` and `bst.instance.Pie64.enable_root_access="0"`. Enable
   root access for Pie64 in the BlueStacks settings (or set both to `"1"` with the
   instance stopped, keep a backup), then restart the instance. **LIVE to check.**
4. **Push + start the server**:
   ```bash
   xz -d frida-server-<ver>-android-<abi>.xz
   "$ADB" -s 127.0.0.1:5555 push frida-server-<ver>-android-<abi> /data/local/tmp/frida-server
   "$ADB" -s 127.0.0.1:5555 shell su -c "chmod 755 /data/local/tmp/frida-server"
   "$ADB" -s 127.0.0.1:5555 shell su -c "/data/local/tmp/frida-server -D -l 127.0.0.1:27142"
   ```
   Port 27142 = `speed_profile.py` `DEFAULT_PORT` (LIVE: HERMES-SETUP); plain `-D`
   listens on frida's default 27042, which `speed_profile.py` reports as rc 4.
   On 27142, `attach.py` needs the adb forward and `--host` (without `--host` it uses
   `-D`, i.e. port 27042).
5. **Check** — the game must be running and logged in:
   ```bash
   "$ADB" -s 127.0.0.1:5555 forward tcp:27142 tcp:27142
   python hack/frida/attach.py ps --host 127.0.0.1:27142
   python hack/frida/attach.py attach hack/frida/probe_timescale.js --host 127.0.0.1:27142 --dry-run
   ```

## Use

```bash
# server on 27142 (step 4): adb forward tcp:27142 tcp:27142 must be set (step 5)
# 1) read-only: what are the current values, who sets timeScale?
python hack/frida/attach.py attach hack/frida/probe_timescale.js --host 127.0.0.1:27142
# 2) measure the baseline first (T61 metrics: .spectre/metrics/battles.jsonl)
# 3) set, then measure again with the same fight type
python hack/frida/attach.py attach hack/frida/set_timescale.js --host 127.0.0.1:27142 --params '{"scale": 1.5}'
python hack/frida/attach.py attach hack/frida/set_timescale.js --host 127.0.0.1:27142 --params '{"scale": 2, "repeat_ms": 1000}'
```

Undo: detach and **restart the game** (the value never persists). Stop the
server: `"$ADB" -s 127.0.0.1:5555 shell su -c "pkill frida-server"`.

## Speed-Profil

`scripts/speed_profile.py` (T80a, ops-hardened in T85) wraps the steps above into
one command. **Live lane only** (touches the device); HERMES-SETUP: Hermes installs
and starts frida-server, the script only checks/uses it.

```bash
python scripts/speed_profile.py on  --scale 2            # set once, frida detaches
python scripts/speed_profile.py on  --scale 1.5 --repeat-ms 1000   # eternalized re-apply
python scripts/speed_profile.py off                      # scale 1
python scripts/speed_profile.py status                   # probe_timescale.js (log-only)
python scripts/speed_profile.py status --json            # one JSON object for scripts
python scripts/speed_profile.py on --dry-run             # print adb/frida commands only
python scripts/speed_profile.py on --server-bin frida-server-<ver>-android-<abi>  # push first
```

**Ports / path / versions** (constants in `speed_profile.py`, all `LIVE:` until Hermes
confirms them): server binary `SERVER=/data/local/tmp/frida-server`, own port
`DEFAULT_PORT=27142` (frida default is 27042; override with `FRIDA_PORT` or `--port`).
Before attaching, the script checks that `frida --version` on the PC equals
`/data/local/tmp/frida-server --version` on the device (mismatch -> rc 4, both versions
printed), that frida-server is running and **listens on the port** (`/proc/net/tcp`,
so a server Hermes started on another port is a clear rc 4, not a misleading
"game not running"), then sets `adb forward tcp:PORT tcp:PORT` and attaches with
`frida -H 127.0.0.1:PORT`.

| rc | meaning |
|---|---|
| 0 | ok |
| 2 | game not running / bad input |
| 3 | frida missing: `frida` / `frida-ps` not on PATH, or `frida --version` answers nothing |
| 4 | server dead/unreachable: no root, binary missing, not running (`status`) or did not start, not listening on the port, PC/server version mismatch, adb push/forward failed, adb hung/unreachable |
| 5 | frida / frida-ps timed out |
| other | frida's own exit code after the attach |

**`status` is read-only**: it never pushes or starts frida-server; a dead server is
rc 4 (only the adb forward is set). `status --json` prints exactly one JSON object on
stdout, every log line goes to stderr:

```json
{"rc": 0, "frida": "17.2.0", "server": {"running": true, "version": "17.2.0", "port": 27142}, "timescale": 1.0, "error": null}
```

`frida`, `server.version` and `timescale` are `null` when unknown (e.g. probe found no
il2cpp); `error` carries the message of the failing step (also for a non-zero frida
exit). `timescale: null` with `rc: 0` means "not observed" — LIVE: `frida -q` may quit
before the probe's 500 ms interval logs the value.

**OFF / restart semantics**: without `--repeat-ms` the scale is set once and frida
detaches; the value stays until the game resets it, `off` sets 1 again. With
`--repeat-ms` the script is `--eternalize`d inside the game and keeps re-applying the
scale — `off` then only wins after a **game restart**.

**Env gate**: not part of the daily run — `afk-bot-watch.sh` / `afk-night.sh` never call
it (a test asserts that). Any future hook must be gated by `AFK_SPEED_PROFILE=1`, which
is **off by default**, until the speed-up is proven live (T61 wall-time metrics).

## Known unknowns (LIVE to check)

- frida 16 vs 17 module API: the scripts try both (`Process.findModuleByName(..).findExportByName`
  and the older `Module.findExportByName`).
- icall names: tried with and without the `()` / `(System.Single)` signature suffix.
- `frida -P <json>` (parameters for `rpc.exports.init`) — present in current frida CLIs;
  if your version lacks it, load the script and call `rpc.exports.set(1.5)` in the REPL.
- Anti-debug / integrity checks of the game: attach after login, watch for disconnects.
- Whether battles respect `Time.timeScale` at all (server-timed fights would not get
  faster) — that is what the T61 wall-time comparison decides.
