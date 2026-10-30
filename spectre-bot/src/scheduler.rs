/// Task scheduler — runs bot actions on a configurable timer loop.
///
/// The scheduler owns the main execution loop: it ticks each enabled task
/// at its configured interval, evaluates guard conditions, and delegates
/// to `BotEngine` for action execution.
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use tokio::time::{Duration, Instant};

use crate::actions::{BotCondition, BotTask};
use crate::engine::BotEngine;

// ── Scheduling State ────────────────────────────────────────────────────────

/// Runtime state for a single scheduled task.
#[derive(Clone)]
struct TaskState {
    /// Copy of the task definition (snapshot at scheduler start).
    task: BotTask,
    /// Last tick instant (for interval calculation).
    last_run: Option<Instant>,
    /// Whether the task is currently active.
    enabled: bool,
    /// Number of consecutive failures.
    fail_count: u32,
}

impl TaskState {
    fn from_task(task: &BotTask) -> TaskState {
        TaskState {
            task: task.clone(),
            last_run: None,
            enabled: task.enabled,
            fail_count: 0,
        }
    }
}

/// Shared control state between the scheduler API and the tick loop.
struct SchedulerState {
    paused: bool,
    shutdown: bool,
}

// ── Scheduler ───────────────────────────────────────────────────────────────

/// Asynchronous task scheduler that drives bot execution on a timer loop.
///
/// # Lifecycle
/// 1. Create with `TaskScheduler::new(...)`.
/// 2. Add tasks with `add_task()` or load from a `BotConfig`.
/// 3. Call `start(engine)` to begin the tick loop (spawns a tokio task).
/// 4. Call `stop()` to signal shutdown and await completion.
/// 5. Use `pause()` / `resume()` for runtime toggling.
///
/// # Thread Safety
/// The scheduler is `Send + Sync`. Its internal state is protected by a
/// `Mutex`, and the tick loop runs on a tokio background task.
pub struct TaskScheduler {
    /// Runtime state for each registered task.
    tasks: Vec<TaskState>,
    /// Global enable flag (overrides per-task enabled).
    global_enabled: bool,
    /// Whether the tick loop is running.
    running: AtomicBool,
    /// Handle to the background tick task (if running).
    tick_task: Arc<Mutex<Option<tokio::task::JoinHandle<()>>>>,
    /// Shared access for stop/pause/resume.
    state: Arc<Mutex<SchedulerState>>,
    /// Default interval for tasks that don't specify one.
    default_interval_ms: u32,
}

impl TaskScheduler {
    /// Create a new scheduler without any tasks.
    ///
    /// `default_interval_ms` is used for tasks that don't specify their own.
    pub fn new(default_interval_ms: u32) -> TaskScheduler {
        TaskScheduler {
            tasks: Vec::new(),
            global_enabled: true,
            running: AtomicBool::new(false),
            tick_task: Arc::new(Mutex::new(None)),
            state: Arc::new(Mutex::new(SchedulerState {
                paused: false,
                shutdown: false,
            })),
            default_interval_ms,
        }
    }

    // ── Task Management ────────────────────────────────────────────────

    /// Add a task to the scheduler. Tasks are snapshotted at start-time.
    pub fn add_task(&mut self, task: &BotTask) {
        self.tasks.push(TaskState::from_task(task));
        tracing::info!(
            "scheduler: added task '{}' (interval={}ms, enabled={})",
            task.name,
            task.interval_ms,
            task.enabled
        );
    }

    /// Remove a task by name. Returns `true` if it was found and removed.
    pub fn remove_task(&mut self, name: &str) -> bool {
        let before = self.tasks.len();
        self.tasks.retain(|ts| ts.task.name != name);
        self.tasks.len() != before
    }

    /// Enable or disable a task by name.
    pub fn set_task_enabled(&mut self, name: &str, enabled: bool) -> bool {
        for ts in &mut self.tasks {
            if ts.task.name == name {
                ts.enabled = enabled;
                tracing::info!(
                    "scheduler: task '{}' {}",
                    name,
                    if enabled { "enabled" } else { "disabled" }
                );
                return true;
            }
        }
        false
    }

    /// Return the list of registered task names.
    pub fn task_names(&self) -> Vec<String> {
        self.tasks
            .iter()
            .map(|ts| ts.task.name.clone())
            .collect::<Vec<String>>()
    }

    /// Return the configured default interval in milliseconds.
    pub fn default_interval_ms(&self) -> u32 {
        self.default_interval_ms
    }

    // ── Lifecycle ──────────────────────────────────────────────────────

    /// Start the background tick loop with the given engine.
    ///
    /// Tasks are snapshotted into the loop; management methods
    /// (`add_task` / `remove_task` / `set_task_enabled`) take effect on
    /// the *next* `start()`. A Ctrl+C signal stops the loop cleanly.
    pub fn start(&self, engine: Arc<BotEngine>) {
        if self.running.swap(true, Ordering::SeqCst) {
            tracing::warn!("scheduler: already running");
            return;
        }

        // Reset shutdown flag for a fresh run.
        self.state.lock().unwrap().shutdown = false;

        let state = Arc::clone(&self.state);
        let tasks = self.tasks.clone();
        let global_enabled = self.global_enabled;
        let default_interval_ms = self.default_interval_ms;

        // Determine tick granularity: use GCD-like minimum of all intervals.
        let intervals: Vec<u32> = tasks
            .iter()
            .map(|ts| {
                if ts.task.interval_ms > 0 {
                    ts.task.interval_ms
                } else {
                    default_interval_ms
                }
            })
            .collect();
        let tick_ms = compute_tick_ms(&intervals);
        tracing::info!(
            "scheduler: starting tick loop at {}ms granularity with {} tasks",
            tick_ms,
            tasks.len()
        );

        let handle = tokio::task::spawn(async move {
            run_tick_loop(
                state,
                tasks,
                global_enabled,
                default_interval_ms,
                tick_ms,
                engine,
            )
            .await;
        });
        *self.tick_task.lock().unwrap() = Some(handle);

        // Ctrl+C handling: signal shutdown so the loop exits cleanly.
        let ctrl_state = Arc::clone(&self.state);
        tokio::task::spawn(async move {
            match tokio::signal::ctrl_c().await {
                Ok(()) => {
                    tracing::info!("scheduler: Ctrl+C received, shutting down");
                    ctrl_state.lock().unwrap().shutdown = true;
                }
                Err(e) => tracing::warn!("scheduler: ctrl_c handler unavailable: {}", e),
            }
        });
    }

    /// Signal the tick loop to shut down and wait for it to finish.
    pub async fn stop(&self) {
        if !self.running.load(Ordering::SeqCst) {
            return;
        }
        self.state.lock().unwrap().shutdown = true;
        let handle = self.tick_task.lock().unwrap().take();
        if let Some(handle) = handle {
            let _ = handle.await;
        }
        self.running.store(false, Ordering::SeqCst);
        tracing::info!("scheduler: stopped");
    }

    /// Pause the tick loop (current tick finishes, then no more until resume).
    pub fn pause(&self) {
        self.state.lock().unwrap().paused = true;
        tracing::info!("scheduler: paused");
    }

    /// Resume a paused tick loop.
    pub fn resume(&self) {
        self.state.lock().unwrap().paused = false;
        tracing::info!("scheduler: resumed");
    }

    /// Toggle global enable/disable (stops action execution, not the loop).
    pub fn set_global_enabled(&mut self, enabled: bool) {
        self.global_enabled = enabled;
        tracing::info!(
            "scheduler: global {}",
            if enabled { "enabled" } else { "disabled" }
        );
    }

    /// Returns `true` if the tick loop is active.
    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    /// Returns `true` if the scheduler is paused.
    pub fn is_paused(&self) -> bool {
        self.state.lock().unwrap().paused
    }
}

// ── Tick Loop ───────────────────────────────────────────────────────────────

/// Core async tick loop. Runs until `shutdown` is signalled.
async fn run_tick_loop(
    state: Arc<Mutex<SchedulerState>>,
    tasks: Vec<TaskState>,
    global_enabled: bool,
    default_interval_ms: u32,
    tick_ms: u32,
    engine: Arc<BotEngine>,
) {
    let mut tasks = tasks;
    let duration = Duration::from_millis(tick_ms as u64);
    let mut tick_count: u64 = 0;

    loop {
        // Check shutdown
        if state.lock().unwrap().shutdown {
            break;
        }

        tick_count += 1;

        // Check pause
        let paused = state.lock().unwrap().paused;
        if !paused {
            tick(&mut tasks, global_enabled, default_interval_ms, &engine).await;
        }

        // Wait for the next tick interval (allows cancellation)
        tokio::time::sleep(duration).await;
    }

    tracing::info!("scheduler: tick loop exited after {} ticks", tick_count);
}

/// Execute one tick: for each task that is due, check guards and run actions.
async fn tick(
    tasks: &mut [TaskState],
    global_enabled: bool,
    default_interval_ms: u32,
    engine: &BotEngine,
) {
    let now = Instant::now();

    for ts in tasks.iter_mut() {
        // 1. Skip disabled tasks or when globally disabled
        if !ts.enabled || !global_enabled {
            continue;
        }

        // 2. Check if the task is due
        let interval_ms = if ts.task.interval_ms > 0 {
            ts.task.interval_ms
        } else {
            default_interval_ms
        };
        let interval = Duration::from_millis(interval_ms as u64);
        let due = ts.last_run.map_or(true, |last| now >= last + interval);
        if !due {
            continue;
        }
        ts.last_run = Some(now);

        // 3. Evaluate guard conditions
        let field_names = collect_guard_field_names(&ts.task.conditions);
        let field_values = if field_names.is_empty() {
            HashMap::new()
        } else {
            let result = engine.ctx().read_fields(&field_names);
            match result {
                Ok(values) => values,
                Err(e) => {
                    tracing::warn!(
                        "task '{}': guard field read failed: {} — skipping tick",
                        ts.task.name,
                        e
                    );
                    ts.fail_count += 1;
                    continue;
                }
            }
        };

        if !ts.task.guard_passes(&field_values) {
            tracing::debug!(
                "task '{}': guard conditions not met — skipping tick",
                ts.task.name
            );
            continue;
        }

        // 4. Execute the action tree
        tracing::info!(
            "task '{}': executing {} actions",
            ts.task.name,
            ts.task.actions.len()
        );
        let results = engine.execute_actions(&ts.task.actions).await;

        // 5. Process results
        let failures = results.iter().filter(|r| r.is_error()).count();
        let stops = results.iter().filter(|r| r.is_stop()).count();

        if failures > 0 {
            ts.fail_count += failures as u32;
            tracing::warn!(
                "task '{}': {} action(s) failed (total failures: {})",
                ts.task.name,
                failures,
                ts.fail_count
            );
        } else {
            ts.fail_count = 0; // reset on clean tick
        }

        if stops > 0 {
            tracing::info!(
                "task '{}': received {} stop signal(s) — disabling",
                ts.task.name,
                stops
            );
            ts.enabled = false;
        }
    }
}

/// Collect unique field names from a list of conditions.
fn collect_guard_field_names(conditions: &[BotCondition]) -> Vec<String> {
    let mut names: Vec<String> = Vec::new();
    for cond in conditions {
        if !names.contains(&cond.field) {
            names.push(cond.field.clone());
        }
    }
    names
}

/// Compute the tick interval as the GCD of all task intervals (min 10ms).
fn compute_tick_ms(intervals: &[u32]) -> u32 {
    if intervals.is_empty() {
        return 100; // default 100ms when there are no tasks
    }
    let mut g = intervals[0];
    for v in &intervals[1..] {
        g = gcd(g, *v);
    }
    g.max(10) // never tick faster than 10ms
}

fn gcd(a: u32, b: u32) -> u32 {
    if b == 0 { a } else { gcd(b, a % b) }
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::actions::{BotAction, LogLevel};
    use crate::engine::ActionContext;

    struct TestCtx(std::sync::atomic::AtomicU32);
    impl ActionContext for TestCtx {
        fn resolve_field(&self, field_name: &str) -> anyhow::Result<Vec<u8>> {
            match field_name {
                "counter" => Ok(self.0.load(Ordering::SeqCst).to_le_bytes().to_vec()),
                _ => anyhow::bail!("unknown field '{}'", field_name),
            }
        }
    }

    #[test]
    fn gcd_and_tick_computation() {
        assert_eq!(gcd(500, 300), 100);
        assert_eq!(compute_tick_ms(&[500, 300]), 100);
        assert_eq!(compute_tick_ms(&[50]), 50);
        assert_eq!(compute_tick_ms(&[]), 100);
    }

    #[tokio::test]
    async fn scheduler_runs_and_stops() {
        let mut sched = TaskScheduler::new(100);
        let task = BotTask {
            name: "tick".into(),
            actions: vec![BotAction::Log {
                level: LogLevel::Debug,
                message: "tick".into(),
            }],
            interval_ms: 10,
            enabled: true,
            conditions: vec![],
        };
        sched.add_task(&task);

        #[derive(Debug, Default)]
        struct DumpReader;
        impl spectre_core::reader::MemoryReader for DumpReader {
            fn backend_kind(&self) -> spectre_core::types::BackendKind {
                spectre_core::types::BackendKind::DumpFile
            }
            fn find_process(
                &self,
                _n: &str,
            ) -> anyhow::Result<Vec<spectre_core::types::ProcessInfo>> {
                Ok(Vec::new())
            }
            fn list_processes(&self) -> anyhow::Result<Vec<spectre_core::types::ProcessInfo>> {
                Ok(Vec::new())
            }
            fn memory_regions(
                &self,
                _p: u32,
            ) -> anyhow::Result<Vec<spectre_core::types::MemoryRegion>> {
                Ok(Vec::new())
            }
            fn process_name(&self, _p: u32) -> anyhow::Result<Option<String>> {
                Ok(None)
            }
            fn read_bytes(&self, _p: u32, _a: u64, _s: u32) -> anyhow::Result<Vec<u8>> {
                Ok(Vec::new())
            }
            fn scan(
                &self,
                _p: u32,
                _pat: Vec<spectre_core::types::ScanPattern>,
                _l: bool,
            ) -> anyhow::Result<Vec<spectre_core::types::ScanReport>> {
                Ok(Vec::new())
            }
        }

        let engine = std::sync::Arc::new(crate::engine::BotEngine::new(
            Box::new(DumpReader),
            Box::new(NoopInput),
            Box::new(TestCtx(std::sync::atomic::AtomicU32::new(0))),
            crate::engine::HookRegistry::new(),
        ));

        sched.start(engine);
        tokio::time::sleep(Duration::from_millis(150)).await;
        assert!(sched.is_running());
        sched.stop().await;
        assert!(!sched.is_running());
    }

    #[derive(Default)]
    struct NoopInput;
    impl crate::engine::InputSimulator for NoopInput {}
}
