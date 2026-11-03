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
   "$ADB" -s 127.0.0.1:5555 shell su -c "/data/local/tmp/frida-server -D"
   ```
5. **Check** — the game must be running and logged in:
   ```bash
   python hack/frida/attach.py ps
   python hack/frida/attach.py attach hack/frida/probe_timescale.js --dry-run
   ```

## Use

```bash
# 1) read-only: what are the current values, who sets timeScale?
python hack/frida/attach.py attach hack/frida/probe_timescale.js
# 2) measure the baseline first (T61 metrics: .spectre/metrics/battles.jsonl)
# 3) set, then measure again with the same fight type
python hack/frida/attach.py attach hack/frida/set_timescale.js --params '{"scale": 1.5}'
python hack/frida/attach.py attach hack/frida/set_timescale.js --params '{"scale": 2, "repeat_ms": 1000}'
```

Undo: detach and **restart the game** (the value never persists). Stop the
server: `"$ADB" -s 127.0.0.1:5555 shell su -c "pkill frida-server"`.

## Known unknowns (LIVE to check)

- frida 16 vs 17 module API: the scripts try both (`Process.findModuleByName(..).findExportByName`
  and the older `Module.findExportByName`).
- icall names: tried with and without the `()` / `(System.Single)` signature suffix.
- `frida -P <json>` (parameters for `rpc.exports.init`) — present in current frida CLIs;
  if your version lacks it, load the script and call `rpc.exports.set(1.5)` in the REPL.
- Anti-debug / integrity checks of the game: attach after login, watch for disconnects.
- Whether battles respect `Time.timeScale` at all (server-timed fights would not get
  faster) — that is what the T61 wall-time comparison decides.
