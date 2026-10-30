/// Core action types, conditions, and task definitions for the spectre-bot engine.
///
/// All types are `Serialize`/`Deserialize`-annotated for YAML config loading.
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::cron::{CronSchedule, parse_cron};

// ── Logging ─────────────────────────────────────────────────────────────────

/// Log severity levels.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LogLevel {
    /// General progress information.
    Info,
    /// Non-critical issues that may need attention.
    Warn,
    /// Critical failures that stop execution.
    Error,
    /// Detailed diagnostic output.
    Debug,
}

impl LogLevel {
    /// Parse a log level from its lowercased string name.
    pub fn parse(s: &str) -> Option<LogLevel> {
        match s.to_lowercase().as_str() {
            "info" => Some(LogLevel::Info),
            "warn" => Some(LogLevel::Warn),
            "error" => Some(LogLevel::Error),
            "debug" => Some(LogLevel::Debug),
            _ => None,
        }
    }

    /// Canonical lowercase name of this level.
    pub fn as_str(self) -> &'static str {
        match self {
            LogLevel::Info => "info",
            LogLevel::Warn => "warn",
            LogLevel::Error => "error",
            LogLevel::Debug => "debug",
        }
    }
}

// ── Conditions ──────────────────────────────────────────────────────────────

/// Supported comparison operators.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ComparisonOp {
    /// Equality (==).
    Eq,
    /// Inequality (!=).
    Neq,
    /// Greater than (>).
    Gt,
    /// Greater than or equal (>=).
    GtEq,
    /// Less than (<).
    Lt,
    /// Less than or equal (<=).
    LtEq,
}

impl ComparisonOp {
    /// Apply the operator to two i64 values.
    pub fn apply_i64(&self, a: i64, b: i64) -> bool {
        match self {
            ComparisonOp::Eq => a == b,
            ComparisonOp::Neq => a != b,
            ComparisonOp::Gt => a > b,
            ComparisonOp::GtEq => a >= b,
            ComparisonOp::Lt => a < b,
            ComparisonOp::LtEq => a <= b,
        }
    }

    /// Apply the operator to two u64 values.
    pub fn apply_u64(&self, a: u64, b: u64) -> bool {
        match self {
            ComparisonOp::Eq => a == b,
            ComparisonOp::Neq => a != b,
            ComparisonOp::Gt => a > b,
            ComparisonOp::GtEq => a >= b,
            ComparisonOp::Lt => a < b,
            ComparisonOp::LtEq => a <= b,
        }
    }

    /// Apply the operator to two f64 values (with a small epsilon for Eq/Neq).
    pub fn apply_f64(&self, a: f64, b: f64) -> bool {
        const EPSILON: f64 = 1e-6;
        match self {
            ComparisonOp::Eq => (a - b).abs() < EPSILON,
            ComparisonOp::Neq => (a - b).abs() >= EPSILON,
            ComparisonOp::Gt => a > b,
            ComparisonOp::GtEq => a >= b,
            ComparisonOp::Lt => a < b,
            ComparisonOp::LtEq => a <= b,
        }
    }

    /// Apply the operator to two byte sequences (Eq/Neq only; panics for others).
    pub fn apply_bytes(&self, a: &[u8], b: &[u8]) -> bool {
        match self {
            ComparisonOp::Eq => a == b,
            ComparisonOp::Neq => a != b,
            _ => panic!("cannot order-compare byte sequences; use Eq or Neq"),
        }
    }
}

/// A concrete value to compare a memory field against.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ValueSpec {
    /// Unsigned integer value.
    U64(u64),
    /// Signed integer value.
    I64(i64),
    /// Floating-point value.
    F64(f64),
    /// Raw byte sequence (for exact matching).
    Bytes(Vec<u8>),
}

/// A condition that reads a named memory field and compares it against a value.
///
/// # Examples
/// ```yaml
/// condition:
///   field: player_hp
///   op: Lt
///   value: !U64 30
/// ```
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BotCondition {
    /// Name of the memory field to read (resolved through the game registry).
    pub field: String,
    /// How to compare the field value.
    pub op: ComparisonOp,
    /// The value to compare against.
    pub value: ValueSpec,
}

impl BotCondition {
    /// Evaluate the condition against a raw (little-endian) field value.
    ///
    /// Returns `true` when the condition holds (e.g. `hp < 30`).
    pub fn evaluate(&self, raw_field_bytes: &[u8]) -> bool {
        match &self.value {
            ValueSpec::U64(expected) => self.op.apply_u64(bytes_to_u64(raw_field_bytes), *expected),
            ValueSpec::I64(expected) => self.op.apply_i64(bytes_to_i64(raw_field_bytes), *expected),
            ValueSpec::F64(expected) => self.op.apply_f64(bytes_to_f64(raw_field_bytes), *expected),
            ValueSpec::Bytes(expected) => self.op.apply_bytes(raw_field_bytes, expected),
        }
    }
}

// ── Actions ─────────────────────────────────────────────────────────────────

/// A single atomic bot action.
///
/// Actions form a tree: `Loop` and `Condition` contain sub-actions,
/// enabling compound bot scripts.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum BotAction {
    /// Read a memory field and run sub-actions only when a condition is met.
    ///
    /// This is the primary polling action — it checks a game-memory field
    /// every time the task runs and conditionally triggers further actions.
    MemoryCheck {
        /// Field name to read (resolved through the game registry).
        field: String,
        /// How to compare the field value.
        op: ComparisonOp,
        /// The value to compare against.
        value: ValueSpec,
    },

    /// Click or tap at screen coordinates.
    InputClick {
        /// Horizontal position (pixels or normalized, backend-dependent).
        x: u32,
        /// Vertical position.
        y: u32,
    },

    /// Swipe / drag gesture from one point to another.
    InputSwipe {
        x1: u32,
        y1: u32,
        x2: u32,
        y2: u32,
        /// Duration of the swipe in milliseconds.
        millis: u64,
    },

    /// Pause execution for a fixed duration.
    Wait {
        /// Milliseconds to wait.
        millis: u64,
    },

    /// Repeat a sequence of actions.
    Loop {
        /// Number of repetitions (0 = infinite / until the tree emits Stop).
        count: u32,
        /// Actions to repeat.
        array: Vec<BotAction>,
    },

    /// Conditional branching — choose one of two sub-actions.
    Condition {
        /// The condition to evaluate.
        cond: BotCondition,
        /// Action run when the condition is true.
        then_: Box<BotAction>,
        /// Action run when the condition is false.
        else_: Option<Box<BotAction>>,
    },

    /// Invoke an external script or hook by name.
    ScriptHook {
        /// Hook identifier (e.g. `"heal_if_low"`, `"auto_loot"`).
        name: String,
    },

    /// Write a log message at the specified severity.
    Log {
        /// Message text.
        message: String,
        /// Severity level.
        level: LogLevel,
    },
}

// ── Tasks ───────────────────────────────────────────────────────────────────

/// A named, schedulable task consisting of a sequence of actions.
///
/// Tasks are the top-level unit of bot configuration. Each task runs
/// independently — either on a fixed `interval_ms` or, when `schedule` is
/// set, on a cron-style schedule — and can be toggled on/off.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BotTask {
    /// Human-readable name for the task (used in logs and debugging).
    pub name: String,
    /// The action tree to execute.
    pub actions: Vec<BotAction>,
    /// Interval between task executions in milliseconds.
    /// `0` (or omitted) means "use the config's `default_interval_ms`".
    /// Ignored for firing when `schedule` is set.
    #[serde(default)]
    pub interval_ms: u32,
    /// Whether this task is enabled at startup.
    pub enabled: bool,
    /// Optional guard conditions; the task only runs when ALL evaluate true.
    pub conditions: Vec<BotCondition>,
    /// Optional five-field cron expression (`minute hour day month weekday`,
    /// local time), e.g. `"*/15 * * * *"`. When set, the task fires at most
    /// once per matching minute instead of every `interval_ms`.
    /// See [`crate::cron`] for the supported syntax.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub schedule: Option<String>,
}

impl BotTask {
    /// Parse this task's `schedule`, if any.
    ///
    /// Errors name the task so a bad expression in a config file is easy
    /// to locate.
    pub fn cron_schedule(&self) -> anyhow::Result<Option<CronSchedule>> {
        match &self.schedule {
            None => Ok(None),
            Some(expr) => parse_cron(expr)
                .map(Some)
                .map_err(|e| anyhow::anyhow!("task '{}': {:#}", self.name, e)),
        }
    }

    /// Check whether all guard conditions pass given the raw field values.
    ///
    /// `field_values` maps field name → raw bytes as read from process memory.
    pub fn guard_passes(&self, field_values: &HashMap<String, Vec<u8>>) -> bool {
        if self.conditions.is_empty() {
            return true;
        }
        self.conditions.iter().all(|cond| {
            field_values
                .get(&cond.field)
                .is_some_and(|bytes| cond.evaluate(bytes))
        })
    }
}

// ── Internal Helpers ────────────────────────────────────────────────────────

/// Interpret raw little-endian bytes as a u64 (zero-extended from shorter types).
pub(crate) fn bytes_to_u64(bytes: &[u8]) -> u64 {
    if bytes.is_empty() {
        return 0;
    }
    let mut buf = [0u8; 8];
    let n = bytes.len().min(8);
    buf[..n].copy_from_slice(&bytes[..n]);
    u64::from_le_bytes(buf)
}

/// Interpret raw little-endian bytes as an i64 (sign-extended from shorter types).
pub(crate) fn bytes_to_i64(bytes: &[u8]) -> i64 {
    if bytes.is_empty() {
        return 0;
    }
    match bytes.len() {
        1 => i8::from_le_bytes([bytes[0]]) as i64,
        2 => i16::from_le_bytes([bytes[0], bytes[1]]) as i64,
        4 => i32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]) as i64,
        _ => i64::from_le_bytes(bytes_to_u64(bytes).to_le_bytes()),
    }
}

/// Interpret raw little-endian bytes as an f64 (4-byte values treated as f32).
pub(crate) fn bytes_to_f64(bytes: &[u8]) -> f64 {
    match bytes.len() {
        4 => f32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]) as f64,
        _ => f64::from_le_bytes(bytes_to_u64(bytes).to_le_bytes()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evaluate_u64_lt() {
        let cond = BotCondition {
            field: "hp".into(),
            op: ComparisonOp::Lt,
            value: ValueSpec::U64(30),
        };
        assert!(cond.evaluate(&20u32.to_le_bytes()));
        assert!(!cond.evaluate(&30u32.to_le_bytes()));
        assert!(!cond.evaluate(&99u32.to_le_bytes()));
    }

    #[test]
    fn evaluate_bytes_eq() {
        let cond = BotCondition {
            field: "tag".into(),
            op: ComparisonOp::Eq,
            value: ValueSpec::Bytes(vec![1, 2, 3]),
        };
        assert!(cond.evaluate(&[1, 2, 3]));
        assert!(!cond.evaluate(&[1, 2, 4]));
    }
}
