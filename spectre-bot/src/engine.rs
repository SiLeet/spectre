/// Bot execution engine — runs sequences of actions with condition evaluation.
///
/// The engine is game-agnostic: actions reference memory fields by name,
/// and an `ActionContext` resolves them to actual values at runtime.
use std::collections::HashMap;

use spectre_core::reader::MemoryReader;

use crate::actions::{BotAction, BotCondition, LogLevel, ValueSpec};

// ── Input Simulation ────────────────────────────────────────────────────────

/// Abstract trait for simulating user input on various backends.
///
/// Implementations exist for ADB (Android Debug Bridge), native OS input
/// (Windows, Linux), and can be user-defined for custom setups.
///
/// All methods return `anyhow::Result` to allow backends to report errors
/// (e.g. device disconnected, permission denied). Every method has a
/// default no-op implementation, so backends only override what they
/// actually support.
pub trait InputSimulator: Send + Sync {
    /// Single tap/click at absolute screen coordinates.
    fn click(&self, _x: u32, _y: u32) -> anyhow::Result<()> {
        Ok(())
    }

    /// Tap and hold at a position for `millis` milliseconds.
    fn tap_hold(&self, _x: u32, _y: u32, _millis: u64) -> anyhow::Result<()> {
        Ok(())
    }

    /// Swipe / drag gesture from (x1,y1) to (x2,y2).
    fn swipe(&self, _x1: u32, _y1: u32, _x2: u32, _y2: u32, _millis: u64) -> anyhow::Result<()> {
        Ok(())
    }

    /// Scroll by a wheel delta (positive = up/away, backend-dependent).
    fn scroll(&self, _delta: i32) -> anyhow::Result<()> {
        Ok(())
    }

    /// Press a single key (e.g. `"enter"`, `"escape"`, `"space"`).
    ///
    /// Key names follow the backend convention (USB HID for ADB, key names
    /// for OS-level simulation).
    fn key(&self, _key: &str) -> anyhow::Result<()> {
        Ok(())
    }
}

// ── Action Context ──────────────────────────────────────────────────────────

/// Resolves named memory fields to raw byte values at runtime.
///
/// This is the bridge between the bot's field-name-based actions and the
/// actual game memory layout defined in `spectre-game` offset files.
///
/// Implementations look up `field_name` in the game's `StructDef` registry,
/// compute the absolute address using the struct's base offset, read the
/// appropriate number of bytes via a `MemoryReader`, and return them.
pub trait ActionContext: Send + Sync {
    /// Read a named memory field and return its raw (little-endian) bytes.
    ///
    /// Returns `Err` when the field name is unknown or the read fails.
    fn resolve_field(&self, field_name: &str) -> anyhow::Result<Vec<u8>>;

    /// Read multiple fields in a single batch (more efficient for polling).
    fn read_fields(&self, field_names: &[String]) -> anyhow::Result<HashMap<String, Vec<u8>>> {
        let mut map = HashMap::new();
        for name in field_names {
            let bytes = self.resolve_field(name)?;
            map.insert(name.clone(), bytes);
        }
        Ok(map)
    }
}

// ── Hook Registry ───────────────────────────────────────────────────────────

/// Signature for a user-defined script hook.
pub type HookFn = fn(&HashMap<String, String>) -> anyhow::Result<()>;

/// Registry of named hooks that `ScriptHook` actions can invoke.
#[derive(Default)]
pub struct HookRegistry {
    hooks: HashMap<String, HookFn>,
}

impl HookRegistry {
    /// Create an empty hook registry.
    pub fn new() -> HookRegistry {
        HookRegistry {
            hooks: HashMap::new(),
        }
    }

    /// Register a hook function by name.
    ///
    /// # Panics
    /// If a hook with the same name is already registered.
    pub fn register(&mut self, name: &str, hook: HookFn) {
        if self.hooks.contains_key(name) {
            panic!("hook '{}' is already registered", name);
        }
        self.hooks.insert(name.to_owned(), hook);
    }

    /// Unregister a hook, returning `true` if it existed.
    pub fn unregister(&mut self, name: &str) -> bool {
        self.hooks.remove(name).is_some()
    }

    /// Check whether a hook exists.
    pub fn has(&self, name: &str) -> bool {
        self.hooks.contains_key(name)
    }

    /// Invoke a hook by name.
    ///
    /// Returns `Err` when the hook is not registered or when it fails.
    pub fn invoke(&self, name: &str, args: &HashMap<String, String>) -> anyhow::Result<()> {
        let available = self
            .hooks
            .keys()
            .cloned()
            .collect::<Vec<String>>()
            .join(", ");
        let hook = self.hooks.get(name).ok_or_else(|| {
            anyhow::anyhow!("hook '{}' not registered; available: {}", name, available)
        })?;
        hook(args)
    }
}

// ── Action Result ───────────────────────────────────────────────────────────

/// Outcome of a single action execution.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ActionResult {
    /// Action completed successfully.
    Ok,
    /// Action completed but produced a warning.
    Warning(String),
    /// Action failed with an error (engine may continue or stop).
    Error(String),
    /// Action signals that the task should stop (e.g. loop broken by condition).
    Stop,
}

impl ActionResult {
    /// Convenience factory for a success.
    pub fn ok() -> ActionResult {
        ActionResult::Ok
    }

    /// Convenience factory for a warning.
    pub fn warn(msg: impl Into<String>) -> ActionResult {
        ActionResult::Warning(msg.into())
    }

    /// Convenience factory for an error.
    pub fn err(msg: impl Into<String>) -> ActionResult {
        ActionResult::Error(msg.into())
    }

    /// Convenience factory for a stop signal.
    pub fn stop() -> ActionResult {
        ActionResult::Stop
    }

    /// Returns `true` when the result indicates execution should stop.
    pub fn is_stop(&self) -> bool {
        matches!(self, ActionResult::Stop)
    }

    /// Returns `true` when the result indicates failure.
    pub fn is_error(&self) -> bool {
        matches!(self, ActionResult::Error(_))
    }
}

// ── Bot Engine ──────────────────────────────────────────────────────────────

/// The core bot engine: evaluates conditions and executes action trees.
///
/// The engine is **task-agnostic at this layer** — it executes a single
/// action tree against a given context. Scheduling and task iteration are
/// handled by `TaskScheduler` (see `scheduler.rs`).
///
/// # Usage
/// ```rust,ignore
/// let engine = BotEngine::new(reader, input, ctx, hooks);
/// let result = engine.run_action(action).await;
/// ```
pub struct BotEngine {
    /// Memory reader for raw reads (exposed via [`BotEngine::reader`]).
    reader: Box<dyn MemoryReader>,
    /// Input simulator used by click/swipe/wait actions.
    input: Box<dyn InputSimulator>,
    /// Memory field resolver (provided by the caller).
    ctx: Box<dyn ActionContext>,
    /// Registered script hooks.
    hooks: HookRegistry,
    /// Maximum depth for nested actions (prevents runaway trees).
    max_depth: u32,
}

impl BotEngine {
    /// Create a new engine instance.
    pub fn new(
        reader: Box<dyn MemoryReader>,
        input: Box<dyn InputSimulator>,
        ctx: Box<dyn ActionContext>,
        hooks: HookRegistry,
    ) -> BotEngine {
        BotEngine {
            reader,
            input,
            ctx,
            hooks,
            max_depth: 64,
        }
    }

    /// Override the maximum nesting depth (default 64).
    pub fn set_max_depth(&mut self, depth: u32) {
        self.max_depth = depth;
    }

    /// Access the underlying memory reader (for raw reads by hooks/bots).
    pub fn reader(&self) -> &dyn MemoryReader {
        self.reader.as_ref()
    }

    /// Access the action context (for guard evaluation by the scheduler).
    pub fn ctx(&self) -> &dyn ActionContext {
        self.ctx.as_ref()
    }

    // ── Public API ──────────────────────────────────────────────────────

    /// Execute a sequence of actions.
    ///
    /// Returns a list of all results (one per action). Each action is
    /// dispatched through the depth-capped recursion of [`BotEngine::run_action`].
    pub async fn execute_actions(&self, actions: &[BotAction]) -> Vec<ActionResult> {
        let mut results = Vec::with_capacity(actions.len());
        for action in actions {
            results.push(self.run_action(action.clone()).await);
        }
        results
    }

    /// Execute a single action tree, with recursion depth capped.
    pub async fn run_action(&self, action: BotAction) -> ActionResult {
        self.run_action_inner(action, 0).await
    }

    async fn run_action_inner(&self, action: BotAction, depth: u32) -> ActionResult {
        if depth > self.max_depth {
            return ActionResult::err(format!("max nesting depth ({}) exceeded", self.max_depth));
        }

        match action {
            BotAction::MemoryCheck { field, op, value } => {
                self.handle_memory_check(&field, op, &value).await
            }
            BotAction::InputClick { x, y } => self.handle_click(x, y).await,
            BotAction::InputSwipe {
                x1,
                y1,
                x2,
                y2,
                millis,
            } => self.handle_swipe(x1, y1, x2, y2, millis).await,
            BotAction::Wait { millis } => self.handle_wait(millis).await,
            BotAction::Loop { count, array } => self.handle_loop(count, array, depth).await,
            BotAction::Condition { cond, then_, else_ } => {
                self.handle_condition(cond, *then_, else_.map(|b| *b), depth)
                    .await
            }
            BotAction::ScriptHook { name } => self.handle_script_hook(&name),
            BotAction::Log { level, message } => self.handle_log(level, &message),
        }
    }

    // ── Handlers ────────────────────────────────────────────────────────

    async fn handle_memory_check(
        &self,
        field: &str,
        op: crate::actions::ComparisonOp,
        value: &ValueSpec,
    ) -> ActionResult {
        match self.ctx.resolve_field(field) {
            Ok(raw) => {
                let cond = BotCondition {
                    field: field.to_owned(),
                    op,
                    value: value.clone(),
                };
                if cond.evaluate(&raw) {
                    tracing::info!("memory check '{}' passed", field);
                    ActionResult::ok()
                } else {
                    tracing::warn!("memory check '{}' failed", field);
                    ActionResult::warn(format!("memory check '{}' failed", field))
                }
            }
            Err(e) => ActionResult::err(format!("memory check '{}' failed: {}", field, e)),
        }
    }

    async fn handle_click(&self, x: u32, y: u32) -> ActionResult {
        tracing::info!("input click at ({}, {})", x, y);
        match self.input.click(x, y) {
            Ok(()) => ActionResult::ok(),
            Err(e) => ActionResult::err(format!("click at ({}, {}) failed: {}", x, y, e)),
        }
    }

    async fn handle_swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, millis: u64) -> ActionResult {
        tracing::info!(
            "input swipe ({}, {}) → ({}, {}) in {}ms",
            x1,
            y1,
            x2,
            y2,
            millis
        );
        match self.input.swipe(x1, y1, x2, y2, millis) {
            Ok(()) => ActionResult::ok(),
            Err(e) => ActionResult::err(format!(
                "swipe ({}, {}) → ({}, {}) failed: {}",
                x1, y1, x2, y2, e
            )),
        }
    }

    async fn handle_wait(&self, millis: u64) -> ActionResult {
        tracing::info!("wait {}ms", millis);
        tokio::time::sleep(tokio::time::Duration::from_millis(millis)).await;
        ActionResult::ok()
    }

    async fn handle_loop(&self, count: u32, array: Vec<BotAction>, depth: u32) -> ActionResult {
        // count == 0 means "until the tree emits Stop".
        let iterations = if count == 0 { u32::MAX } else { count };
        let mut done: u32 = 0;
        while done < iterations {
            done += 1;
            tracing::info!(
                "loop iteration {}/{}",
                done,
                if count == 0 {
                    "∞".to_owned()
                } else {
                    count.to_string()
                }
            );
            for action in &array {
                let result = Box::pin(self.run_action_inner(action.clone(), depth + 1)).await;
                if result.is_stop() {
                    tracing::info!("loop stopped early at iteration {}", done);
                    return result;
                }
                if result.is_error() {
                    return result;
                }
            }
        }
        ActionResult::ok()
    }

    async fn handle_condition(
        &self,
        cond: BotCondition,
        then_: BotAction,
        else_: Option<BotAction>,
        depth: u32,
    ) -> ActionResult {
        match self.ctx.resolve_field(&cond.field) {
            Ok(raw) => {
                let passes = cond.evaluate(&raw);
                tracing::info!(
                    "condition '{}' is {} — taking {} branch",
                    cond.field,
                    passes,
                    if passes { "then" } else { "else" }
                );
                if passes {
                    Box::pin(self.run_action_inner(then_, depth + 1)).await
                } else if let Some(else_action) = else_ {
                    Box::pin(self.run_action_inner(else_action, depth + 1)).await
                } else {
                    ActionResult::ok()
                }
            }
            Err(e) => ActionResult::err(format!("condition '{}' failed: {}", cond.field, e)),
        }
    }

    fn handle_script_hook(&self, name: &str) -> ActionResult {
        tracing::info!("script hook '{}'", name);
        let args = HashMap::new();
        match self.hooks.invoke(name, &args) {
            Ok(()) => ActionResult::ok(),
            Err(e) => ActionResult::err(format!("hook '{}' failed: {}", name, e)),
        }
    }

    fn handle_log(&self, level: LogLevel, message: &str) -> ActionResult {
        match level {
            LogLevel::Info => tracing::info!("[bot] {}", message),
            LogLevel::Warn => tracing::warn!("[bot] {}", message),
            LogLevel::Error => tracing::error!("[bot] {}", message),
            LogLevel::Debug => tracing::debug!("[bot] {}", message),
        }
        ActionResult::ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::actions::ComparisonOp;

    struct TestCtx;
    impl ActionContext for TestCtx {
        fn resolve_field(&self, field_name: &str) -> anyhow::Result<Vec<u8>> {
            match field_name {
                "hp" => Ok(20u32.to_le_bytes().to_vec()),
                _ => anyhow::bail!("unknown field '{}'", field_name),
            }
        }
    }

    #[derive(Debug)]
    struct TestReader;
    impl MemoryReader for TestReader {
        fn backend_kind(&self) -> spectre_core::types::BackendKind {
            spectre_core::types::BackendKind::DumpFile
        }
        fn find_process(
            &self,
            _name: &str,
        ) -> anyhow::Result<Vec<spectre_core::types::ProcessInfo>> {
            Ok(Vec::new())
        }
        fn list_processes(&self) -> anyhow::Result<Vec<spectre_core::types::ProcessInfo>> {
            Ok(Vec::new())
        }
        fn memory_regions(
            &self,
            _pid: u32,
        ) -> anyhow::Result<Vec<spectre_core::types::MemoryRegion>> {
            Ok(Vec::new())
        }
        fn process_name(&self, _pid: u32) -> anyhow::Result<Option<String>> {
            Ok(None)
        }
        fn read_bytes(&self, _pid: u32, _address: u64, _size: u32) -> anyhow::Result<Vec<u8>> {
            Ok(Vec::new())
        }
        fn scan(
            &self,
            _pid: u32,
            _patterns: Vec<spectre_core::types::ScanPattern>,
            _little: bool,
        ) -> anyhow::Result<Vec<spectre_core::types::ScanReport>> {
            Ok(Vec::new())
        }
    }

    fn make_engine() -> BotEngine {
        BotEngine::new(
            Box::new(TestReader),
            Box::new(NoopInput::default()),
            Box::new(TestCtx),
            HookRegistry::new(),
        )
    }

    #[derive(Default)]
    struct NoopInput;
    impl InputSimulator for NoopInput {}

    #[tokio::test]
    async fn condition_branch_then() {
        let engine = make_engine();
        let action = BotAction::Condition {
            cond: BotCondition {
                field: "hp".into(),
                op: ComparisonOp::Lt,
                value: ValueSpec::U64(30),
            },
            then_: Box::new(BotAction::Log {
                level: LogLevel::Info,
                message: "heal".into(),
            }),
            else_: None,
        };
        let result = engine.run_action(action).await;
        assert_eq!(result, ActionResult::Ok);
    }

    #[tokio::test]
    async fn depth_cap_returns_error() {
        let engine = make_engine();
        let mut action = BotAction::Wait { millis: 1 };
        for _ in 0..70 {
            action = BotAction::Loop {
                count: 1,
                array: vec![action],
            };
        }
        let result = engine.run_action(action).await;
        assert!(result.is_error());
    }
}
