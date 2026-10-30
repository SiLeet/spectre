/// spectre-lua — Lua scripting bindings for Spectre bot automation.
///
/// Provides a sandboxed Lua 5.x environment with `spectre` and `bot` modules
/// that expose memory reading, scanning, and automation primitives.
pub mod api;

use mlua::{Lua, Nil, Value};
use spectre_core::MemoryReader;

// ── Bot API ─────────────────────────────────────────────────────────

/// Interface for bot input actions callable from Lua scripts.
///
/// Implementors provide the actual click/swipe/wait/log primitives
/// (e.g. via ADB input, Windows input, or an Android emulator).
pub trait BotApi: Send + Sync + 'static {
    /// Tap/click at screen pixel coordinate (x, y).
    /// Returns true if the action was acknowledged.
    fn click(&self, x: u32, y: u32) -> anyhow::Result<bool>;

    /// Perform a swipe/drag from (x1, y1) to (x2, y2) over `duration_ms`.
    fn swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, duration_ms: u32) -> anyhow::Result<bool>;

    /// Sleep (non-busy-wait) for `ms` milliseconds.
    fn wait(&self, ms: u32) -> anyhow::Result<()>;

    /// Emit a log message from a running Lua script.
    fn log(&self, message: &str) -> anyhow::Result<()>;
}

// ── Context stored as Lua app-data ─────────────────────────────────

/// Owned context that Lua callbacks retrieve via `app_data_ref`.
///
/// Kept alive inside the Lua instance for the sandbox's entire lifetime.
pub struct LuaContext {
    pub reader: Box<dyn MemoryReader + Send + 'static>,
    pub bot: Box<dyn BotApi + Send + 'static>,
}

// ── LuaSandbox ──────────────────────────────────────────────────────

/// A sandboxed Lua 5.4 runtime with Spectre bindings pre-registered.
///
/// Usage:
/// ```ignore
/// let reader: Box<dyn MemoryReader + Send + 'static> = …;
/// let bot:    Box<dyn BotApi + Send + 'static>    = …;
/// let sandbox = LuaSandbox::create(reader, bot)?;
/// sandbox.run(r#"bot.log("hello from Lua")"#)?;
/// ```
pub struct LuaSandbox {
    lua: Lua,
}

impl LuaSandbox {
    /// Create a new sandbox, register all modules, and transfer ownership
    /// of the backend objects into the Lua instance.
    pub fn create(
        reader: Box<dyn MemoryReader + Send + 'static>,
        bot: Box<dyn BotApi + Send + 'static>,
    ) -> anyhow::Result<LuaSandbox> {
        let lua = Lua::new();
        let ctx = LuaContext { reader, bot };

        // Move context into the Lua instance so callbacks can retrieve it.
        // Note: mlua's set_app_data returns the *previous* value (Option),
        // not a Result — there is nothing to propagate here.
        lua.set_app_data(ctx);

        // Register spectre and bot modules
        api::LuaApi::register(&lua)?;

        tracing::info!("spectre-lua sandbox ready");
        Ok(LuaSandbox { lua })
    }

    /// Execute a Lua script string.
    pub fn run(&self, script: &str) -> anyhow::Result<()> {
        self.lua.load(script).exec()?;
        Ok(())
    }

    /// Execute a Lua script file.
    pub fn run_file(&self, path: &str) -> anyhow::Result<()> {
        let source = std::fs::read_to_string(path)?;
        self.lua.load(source).set_name(path).exec()?;
        Ok(())
    }

    /// Evaluate a Lua expression and return the result as type `T`.
    pub fn eval<T>(&self, expr: &str) -> anyhow::Result<T>
    where
        T: mlua::FromLuaMulti,
    {
        Ok(self.lua.load(expr).eval::<T>()?)
    }

    /// Hot-reload: re-run the given script without recreating the sandbox.
    /// The Lua state (global variables, etc.) persists across calls.
    /// The `spectre` and `bot` modules are preserved; all other user
    /// globals are cleared before the new script loads.
    pub fn reload(&self, script: &str) -> anyhow::Result<()> {
        let globals = self.lua.globals();

        // Preserve our modules and the standard-library globals
        let keep: &[&str] = &["spectre", "bot", "_G", "_VERSION"];

        // Collect user-global keys first (we cannot mutate the table while
        // iterating it).
        let mut keys: Vec<Value> = Vec::new();
        for pair in globals.pairs::<Value, Value>() {
            let (key, _): (Value, Value) = pair?;
            keys.push(key);
        }

        // Clear all user globals, skipping built-in modules.
        for key in keys {
            let name = key.as_string().map(|s| s.to_string_lossy());
            if let Some(name) = name {
                if keep.contains(&name.as_str()) {
                    continue;
                }
            }
            globals.set(key, Nil)?;
        }

        // Load and execute the new script
        self.lua.load(script).exec()?;
        Ok(())
    }

    /// Access the underlying Lua instance (e.g. for advanced inspection).
    pub fn lua(&self) -> &Lua {
        &self.lua
    }

    /// Retrieve a reference to the stored context.
    ///
    /// Returns a guard that dereferences to [`LuaContext`]; it is released
    /// when the returned value is dropped.
    pub fn context(&self) -> mlua::AppDataRef<'_, LuaContext> {
        self.lua
            .app_data_ref::<LuaContext>()
            .expect("LuaContext app data must be set before create returns")
    }
}
