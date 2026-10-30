/// Serializable YAML configuration for the spectre-bot engine.
///
/// # Example
/// ```yaml
/// # spectre-bot.yaml
/// default_interval_ms: 500
/// input_backend: adb
/// memory_poll_ms: 100
/// enabled: true
/// tasks:
///   - name: auto_heal
///     interval_ms: 300
///     enabled: true
///     conditions:
///       - field: player_hp
///         op: Lt
///         value: !U64 30
///     actions:
///       - MemoryCheck:
///           field: player_hp
///           op: Lt
///           value: !U64 30
///       - InputClick:
///           x: 400
///           y: 600
///       - Wait:
///           millis: 2000
/// ```
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::actions::BotTask;

/// Top-level bot configuration, typically loaded from a YAML file.
///
/// This structure drives the entire bot engine: it defines which tasks
/// to run, at what interval, through which input backend, and how often
/// to poll game memory.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct BotConfig {
    /// Ordered list of bot tasks. Each task is independently scheduled.
    #[serde(default)]
    pub tasks: Vec<BotTask>,

    /// Default interval (ms) between task iterations when the task itself
    /// does not specify one.
    #[serde(default = "default_interval_ms")]
    pub default_interval_ms: u32,

    /// Input backend identifier: `"adb"`, `"native_windows"`, `"native_linux"`,
    /// or a custom name registered with the engine.
    #[serde(default = "default_input_backend")]
    pub input_backend: String,

    /// Minimum interval (ms) between successive memory polls across all tasks.
    /// Higher values reduce pressure on the memory-reader backend.
    #[serde(default = "default_memory_poll_ms")]
    pub memory_poll_ms: u32,

    /// Global enable/disable switch. When `false`, the scheduler loop runs
    /// but skips all action execution.
    #[serde(default = "default_enabled")]
    pub enabled: bool,

    /// Arbitrary key-value metadata (e.g. game name, version, author).
    #[serde(default)]
    pub metadata: Option<HashMap<String, String>>,
}

fn default_interval_ms() -> u32 {
    500
}

fn default_input_backend() -> String {
    "adb".to_owned()
}

fn default_memory_poll_ms() -> u32 {
    100
}

fn default_enabled() -> bool {
    true
}

impl BotConfig {
    /// Create a default configuration.
    /// (Inherent; the struct also derives `Default` for serde field defaults.)
    #[allow(clippy::should_implement_trait)]
    pub fn default() -> BotConfig {
        BotConfig {
            tasks: Vec::new(),
            default_interval_ms: default_interval_ms(),
            input_backend: default_input_backend(),
            memory_poll_ms: default_memory_poll_ms(),
            enabled: default_enabled(),
            metadata: None,
        }
    }

    /// Load a `BotConfig` from a YAML string.
    pub fn from_yaml(yaml_text: &str) -> anyhow::Result<BotConfig> {
        serde_yaml::from_str::<BotConfig>(yaml_text)
            .map_err(|e| anyhow::anyhow!("failed to parse bot config: {}", e))
    }

    /// Load a `BotConfig` from a YAML file on disk.
    pub fn from_yaml_file(path: &str) -> anyhow::Result<BotConfig> {
        let text = std::fs::read_to_string(path)?;
        BotConfig::from_yaml(&text)
    }

    /// Serialize this config back to a YAML string.
    pub fn to_yaml(&self) -> anyhow::Result<String> {
        serde_yaml::to_string(self)
            .map_err(|e| anyhow::anyhow!("failed to serialize bot config: {}", e))
    }

    /// Find a task by name. Returns `None` when no task matches.
    pub fn find_task(&self, name: &str) -> Option<&BotTask> {
        self.tasks.iter().find(|t| t.name == name)
    }

    /// Return all enabled tasks.
    pub fn enabled_tasks(&self) -> Vec<&BotTask> {
        self.tasks
            .iter()
            .filter(|t| t.enabled)
            .collect::<Vec<&BotTask>>()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn yaml_roundtrip() {
        let cfg = BotConfig::default();
        let yaml = cfg.to_yaml().unwrap();
        let back = BotConfig::from_yaml(&yaml).unwrap();
        assert_eq!(cfg, back);
    }

    #[test]
    fn parse_partial_yaml() {
        let yaml = "tasks: []\n";
        let cfg = BotConfig::from_yaml(yaml).unwrap();
        assert_eq!(cfg.tasks.len(), 0);
        assert_eq!(cfg.input_backend, "adb");
        assert!(cfg.enabled);
    }
}
