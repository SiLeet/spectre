/// spectre-bot — Bot execution engine with task scheduling and action primitives.
///
/// This crate provides a game-agnostic bot execution engine for Spectre.
/// Actions reference memory fields by name (resolved through an
/// `ActionContext`), and input simulation is abstracted behind an
/// `InputSimulator` trait, enabling the same bot scripts to work across
/// ADB (Android), native Windows input, and other backends.
pub mod actions;
pub mod config;
pub mod cron;
pub mod engine;
pub mod scheduler;
#[cfg(windows)]
pub mod wininput;

// Re-export key types at the crate root for convenience.
pub use actions::{BotAction, BotCondition, BotTask, ComparisonOp, LogLevel, ValueSpec};
pub use config::BotConfig;
pub use engine::{ActionContext, ActionResult, BotEngine, HookRegistry, InputSimulator};
pub use scheduler::TaskScheduler;
#[cfg(windows)]
pub use wininput::WindowsInput;
