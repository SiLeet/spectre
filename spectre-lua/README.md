# spectre-lua

Lua scripting bindings for the [Spectre](https://github.com/sergej-dukart/spectre) game-memory automation toolkit.

Provides a sandboxed Lua 5.x runtime with two built-in modules — `spectre` (memory reading and scanning) and `bot` (input automation) — so you can script game bot logic in Lua without restarting the Rust runtime.

## Features

- **Hot-reloadable** — iterate on Lua scripts without restarting the process.
- **Fully sandboxed** — each script runs inside a fresh Lua state with only the `spectre` and `bot` modules exposed.
- **All standard Lua libraries** — string, table, math, and io operations available.
- **Works with any `MemoryReader` backend** — ADB, native Windows/Linux, or dump-file readers.
- **Extensible `BotApi` trait** — plug in any automation backend (ADB input, Win32 API, XDotool).

## API Reference

### `spectre` module

```lua
-- Read a 32-bit unsigned integer from process memory
local hp = spectre.read_u32(pid, address)  -- -> number

-- Read a 32-bit float from process memory
local hp_float = spectre.read_f32(pid, address)  -- -> number

-- Read a string from process memory (null-terminated, up to `length` bytes)
local name = spectre.read_string(pid, address, length)  -- -> string

-- Scan memory for structured patterns
-- patterns is a table of field descriptors:
--   { name = "field_name", type = "u32", value = { exact = { 0x00, 0x00, 0x80, 0x3F } } }
-- Returns a table mapping pattern names to arrays of match tables
local results = spectre.scan({
    { name = "hp",    type = "u32", value = { int = { lo = 0, hi = 9999 } } },
    { name = "level", type = "u32", value = { any = true } },
})

-- Find a process by name (partial match), returns pid or nil
local pid = spectre.find_process("game.exe")
-- -> number | nil
```

#### `spectre.scan()` field types

| Type string | Description |
|-------------|-------------|
| `"u8"` `"u16"` `"u32"` `"u64"` | Unsigned integers |
| `"i8"` `"i16"` `"i32"` `"i64"` | Signed integers |
| `"f32"` `"f64"` | Floating point |

#### `spectre.scan()` value matchers

| Matcher | Lua shape |
|---------|-----------|
| Exact bytes | `{ exact = { 0x12, 0x34, ... } }` |
| Integer range | `{ int = { lo = -100, hi = 1000 } }` |
| Float range | `{ float = { lo = 0.0, hi = 1.0 } }` |
| Any value | `{ any = true }` |

### `bot` module

```lua
-- Click at screen coordinates. Returns true if acknowledged.
local ok = bot.click(x, y)  -- -> boolean

-- Perform a swipe/drag gesture.
local ok = bot.swipe(x1, y1, x2, y2, duration_ms)  -- -> boolean

-- Sleep (non-busy-wait) for a number of milliseconds.
bot.wait(ms)  -- -> nil

-- Log a message from the script (appears in the Rust-side trace log).
bot.log("hello from script")  -- -> nil
```

## Getting Started

### Rust integration

```rust
use spectre_lua::{LuaSandbox, BotApi};
use spectre_core::MemoryReader;

// Your bot backend must implement BotApi
struct MyBot;
impl BotApi for MyBot {
    fn click(&self, x: u32, y: u32) -> anyhow::Result<bool> { /* ... */ }
    fn swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, dur: u32) -> anyhow::Result<bool> { /* ... */ }
    fn wait(&self, ms: u32) -> anyhow::Result<()> { std::thread::sleep(ms); Ok(()) }
    fn log(&self, msg: &str) -> anyhow::Result<()> { traced::info!("[lua] {}", msg); Ok(()) }
}

// Create the sandbox
let reader: Box<dyn MemoryReader + Send + 'static> = …;
let bot:    Box<dyn BotApi + Send + 'static>    = Box::new(MyBot());
let sandbox = LuaSandbox::create(reader, bot)?;

// Run a script
sandbox.run(r#"
    local pid = spectre.find_process("mygame")
    if pid then
        local hp = spectre.read_u32(pid, 0x12345678)
        bot.log("HP: " .. hp)
    end
"#)?;

// Hot-reload: re-run with a modified script, state preserved
sandbox.reload("…")?;
```

### From the CLI

If you're using `spectre-cli`, pass `--lua script.lua` to run a Lua file directly:

```bash
cargo run --bin spectre -- --backend native --lua examples/afk-bot.lua
```

## Hot-Reloading

Call `sandbox.reload(script)` to re-execute a script. The Lua state **persists** — global variables defined in the previous run live on, but are cleared before the new script runs (`spectre` and `bot` modules are preserved). This lets you:

1. Open a Lua file in your editor
2. Save → trigger reload
3. See results without restarting the process

## Dependencies

- [`mlua`](https://crates.io/crates/mlua) — high-level Rust bindings to Lua 5.x
- [`spectre-core`](https://crates.io/crates/spectre-core) — memory reader trait and scan engine

## License

MIT — see the [Spectre repository](https://github.com/sergej-dukart/spectre) for details.