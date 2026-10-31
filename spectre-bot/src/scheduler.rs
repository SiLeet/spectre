/// Task scheduler — runs bot actions on a configurable timer loop.
///
/// The scheduler owns the main execution loop: it ticks each enabled task
/// at its configured interval (or, for tasks with a cron `schedule`, once
/// per matching local-time minute), evaluates guard conditions, and
/// delegates to `BotEngine` for action execution.
///
/// Per-task semantics (also what `spectre bot` uses):
/// - Firing: `schedule` (cron) > `interval_ms` > config `default_interval_ms`.
///   A cron task starts at most once per matching local minute; an interval
///   task at most once per interval, measured per task from its last slot.
///   An interval task's first slot is the first tick after `start()`.
/// - A due task consumes its slot, then its head `conditions` are checked:
///   all true -> actions run; any false -> skipped until the next slot; a
///   failed field read -> skipped (logged, counted as a failure), the loop
///   and the other tasks keep running.
/// - Every skip is logged with its reason (debug; failed reads at warn).
/// - A `Stop` result disables the task for the rest of the run.
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use chrono::{DateTime, TimeZone};
use tokio::sync::Notify;
use tokio::time::{Duration, Instant};

use crate::actions::{BotCondition, BotTask};
use crate::config::BotConfig;
use crate::cron::CronTrigger;
use crate::engine::BotEngine;

/// Upper bound for the tick period whenever at least one cron-scheduled task
/// is registered. Well below 60 s so that no matching minute is skipped even
/// with loop drift; it is folded into the GCD so interval tasks stay aligned.
const CRON_TICK_MS: u32 = 1000;

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
    /// Cron trigger when the task has a `schedule` (overrides `interval_ms`).
    cron: Option<CronTrigger>,
}

impl TaskState {
    fn from_task(task: &BotTask) -> anyhow::Result<TaskState> {
        Ok(TaskState {
            task: task.clone(),
            last_run: None,
            enabled: task.enabled,
            fail_count: 0,
            cron: task.cron_schedule()?.map(CronTrigger::new),
        })
    }
}

/// Shared control state between the scheduler API and the tick loop.
struct SchedulerState {
    paused: bool,
    shutdown: bool,
    /// Wakes the tick loop out of a tick or its sleep on shutdown.
    wake: Arc<Notify>,
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
                wake: Arc::new(Notify::new()),
            })),
            default_interval_ms,
        }
    }

    /// Create a scheduler with all tasks, the default interval and the
    /// global `enabled` switch of `config`.
    pub fn from_config(config: &BotConfig) -> anyhow::Result<TaskScheduler> {
        let mut sched = TaskScheduler::new(config.default_interval_ms);
        sched.global_enabled = config.enabled;
        for task in &config.tasks {
            sched.add_task(task)?;
        }
        Ok(sched)
    }

    // ── Task Management ────────────────────────────────────────────────

    /// Add a task to the scheduler. Tasks are snapshotted at start-time.
    ///
    /// Fails (without adding the task) if the task's cron `schedule` is
    /// invalid; the error names the task.
    pub fn add_task(&mut self, task: &BotTask) -> anyhow::Result<()> {
        let state = TaskState::from_task(task)?;
        match &state.cron {
            Some(trigger) => tracing::info!(
                "scheduler: added task '{}' (schedule='{}', enabled={})",
                task.name,
                trigger.schedule(),
                task.enabled
            ),
            None => tracing::info!(
                "scheduler: added task '{}' (interval={}ms, enabled={})",
                task.name,
                task.effective_interval_ms(self.default_interval_ms),
                task.enabled
            ),
        }
        self.tasks.push(state);
        Ok(())
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

        // Reset shutdown flag and wake-up for a fresh run.
        let wake = {
            let mut st = self.state.lock().unwrap();
            st.shutdown = false;
            st.wake = Arc::new(Notify::new());
            Arc::clone(&st.wake)
        };

        let state = Arc::clone(&self.state);
        let tasks = self.tasks.clone();
        let global_enabled = self.global_enabled;
        let default_interval_ms = self.default_interval_ms;

        // Determine tick granularity: GCD of all intervals (capped for cron).
        let tick_ms = tick_ms_for_tasks(&tasks, default_interval_ms);
        tracing::info!(
            "scheduler: starting tick loop at {}ms granularity with {} tasks",
            tick_ms,
            tasks.len()
        );

        let loop_wake = Arc::clone(&wake);
        let handle = tokio::task::spawn(async move {
            run_tick_loop(
                state,
                tasks,
                global_enabled,
                default_interval_ms,
                tick_ms,
                engine,
                loop_wake,
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
                    wake.notify_one();
                }
                Err(e) => tracing::warn!("scheduler: ctrl_c handler unavailable: {}", e),
            }
        });
    }

    /// Signal the tick loop to shut down and wait for it to finish.
    ///
    /// An in-flight tick is cancelled at its next `.await` point.
    pub async fn stop(&self) -> Result<(), tokio::task::JoinError> {
        if !self.running.load(Ordering::SeqCst) {
            return Ok(());
        }
        {
            let mut st = self.state.lock().unwrap();
            st.shutdown = true;
            st.wake.notify_one();
        }
        let result = self.wait().await;
        tracing::info!("scheduler: stopped");
        result
    }

    /// Wait until the tick loop exits (after `stop()` or Ctrl+C).
    ///
    /// Returns the join error if the tick loop panicked.
    pub async fn wait(&self) -> Result<(), tokio::task::JoinError> {
        let handle = self.tick_task.lock().unwrap().take();
        let result = match handle {
            Some(handle) => handle.await,
            None => Ok(()),
        };
        if let Err(e) = &result {
            tracing::error!("scheduler: tick loop failed: {}", e);
        }
        self.running.store(false, Ordering::SeqCst);
        result
    }

    /// Run every enabled task once, now, ignoring `schedule` / interval
    /// timing but still checking head `conditions` (for `bot --once`).
    pub async fn run_once(&mut self, engine: &BotEngine) {
        if !self.global_enabled {
            tracing::debug!("scheduler: globally disabled — nothing to run");
            return;
        }
        for ts in self.tasks.iter_mut().filter(|ts| ts.enabled) {
            run_task(ts, engine).await;
        }
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
    wake: Arc<Notify>,
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
        let tick_and_sleep = async {
            if !paused {
                tick(
                    &mut tasks,
                    global_enabled,
                    default_interval_ms,
                    &engine,
                    Instant::now(),
                    &chrono::Local::now(),
                )
                .await;
            }
            tokio::time::sleep(duration).await;
        };

        // Shutdown cancels both the running tick and the wait for the next.
        tokio::select! {
            _ = tick_and_sleep => {}
            _ = wake.notified() => break,
        }
    }

    tracing::info!("scheduler: tick loop exited after {} ticks", tick_count);
}

/// Execute one tick: for each task that is due, check guards and run actions.
///
/// `now` drives interval tasks and `wall_now` cron tasks; both are passed
/// in so tests can step time without sleeping.
async fn tick<Tz: TimeZone>(
    tasks: &mut [TaskState],
    global_enabled: bool,
    default_interval_ms: u32,
    engine: &BotEngine,
    now: Instant,
    wall_now: &DateTime<Tz>,
) {
    for ts in tasks.iter_mut() {
        // 1. Skip disabled tasks or when globally disabled
        if !ts.enabled || !global_enabled {
            continue;
        }

        // 2. Check if the task is due. Cron tasks fire at most once per
        //    matching minute (the minute is consumed even if the guard
        //    below fails, mirroring how interval tasks consume their slot).
        let due = match ts.cron.as_mut() {
            Some(trigger) => {
                let due = trigger.should_fire(wall_now);
                if !due {
                    tracing::debug!(
                        "task '{}': not a new '{}' minute — skipping",
                        ts.task.name,
                        trigger.schedule()
                    );
                }
                due
            }
            None => {
                let interval_ms = ts.task.effective_interval_ms(default_interval_ms);
                let interval = Duration::from_millis(interval_ms as u64);
                let due = ts.last_run.is_none_or(|last| now >= last + interval);
                if !due {
                    tracing::debug!(
                        "task '{}': interval {}ms not elapsed — skipping",
                        ts.task.name,
                        interval_ms
                    );
                }
                due
            }
        };
        if !due {
            continue;
        }
        ts.last_run = Some(now);

        run_task(ts, engine).await;
    }
}

/// Check a task's head conditions and, if they pass, run its actions.
async fn run_task(ts: &mut TaskState, engine: &BotEngine) {
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
                return;
            }
        }
    };

    if !ts.task.guard_passes(&field_values) {
        tracing::debug!(
            "task '{}': guard conditions not met — skipping tick",
            ts.task.name
        );
        return;
    }

    // 4. Execute the action tree
    tracing::info!(
        "task '{}': executing {} actions",
        ts.task.name,
        ts.task.actions.len()
    );
    let results = engine.execute_actions(&ts.task.actions).await;

    // 5. Process results
    for r in &results {
        if let crate::engine::ActionResult::Error(e) = r {
            tracing::warn!("task '{}': error: {}", ts.task.name, e);
        }
    }
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

/// Tick period for a task set: GCD of the interval tasks' periods, with
/// [`CRON_TICK_MS`] folded in when any task is cron-scheduled (so the tick
/// never exceeds it). Cron tasks' own `interval_ms` does not contribute.
fn tick_ms_for_tasks(tasks: &[TaskState], default_interval_ms: u32) -> u32 {
    let mut intervals: Vec<u32> = tasks
        .iter()
        .filter(|ts| ts.cron.is_none())
        .map(|ts| ts.task.effective_interval_ms(default_interval_ms))
        .collect();
    if tasks.iter().any(|ts| ts.cron.is_some()) {
        intervals.push(CRON_TICK_MS);
    }
    compute_tick_ms(&intervals)
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

    #[derive(Debug, Default)]
    struct DumpReader;
    impl spectre_core::reader::MemoryReader for DumpReader {
        fn backend_kind(&self) -> spectre_core::types::BackendKind {
            spectre_core::types::BackendKind::DumpFile
        }
        fn find_process(&self, _n: &str) -> anyhow::Result<Vec<spectre_core::types::ProcessInfo>> {
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
            schedule: None,
        };
        sched.add_task(&task).unwrap();

        let engine = std::sync::Arc::new(crate::engine::BotEngine::new(
            Box::new(DumpReader),
            Box::new(NoopInput),
            Box::new(TestCtx(std::sync::atomic::AtomicU32::new(0))),
            crate::engine::HookRegistry::new(),
        ));

        sched.start(engine);
        tokio::time::sleep(Duration::from_millis(150)).await;
        assert!(sched.is_running());
        sched.stop().await.unwrap();
        assert!(!sched.is_running());
    }

    fn task(name: &str, interval_ms: u32, schedule: Option<&str>) -> BotTask {
        BotTask {
            name: name.into(),
            actions: vec![],
            interval_ms,
            enabled: true,
            conditions: vec![],
            schedule: schedule.map(str::to_owned),
        }
    }

    fn states(tasks: &[BotTask]) -> Vec<TaskState> {
        tasks
            .iter()
            .map(|t| TaskState::from_task(t).unwrap())
            .collect()
    }

    #[test]
    fn interval_only_tick_unchanged() {
        let ts = states(&[task("a", 500, None), task("b", 300, None)]);
        assert_eq!(tick_ms_for_tasks(&ts, 100), 100);
        // interval_ms = 0 falls back to the default interval, as before.
        let ts = states(&[task("a", 0, None)]);
        assert_eq!(tick_ms_for_tasks(&ts, 5000), 5000);
        assert_eq!(tick_ms_for_tasks(&[], 5000), 100);
    }

    #[test]
    fn cron_tasks_cap_tick_below_a_minute() {
        // Cron-only task without interval_ms: default interval is ignored.
        let ts = states(&[task("c", 0, Some("*/15 * * * *"))]);
        assert_eq!(tick_ms_for_tasks(&ts, 120_000), CRON_TICK_MS);

        // A large interval_ms on a cron task does not slow the tick.
        let ts = states(&[task("c", 3_600_000, Some("0 * * * *"))]);
        assert_eq!(tick_ms_for_tasks(&ts, 500), CRON_TICK_MS);

        // Mixed: GCD keeps interval tasks aligned and stays <= CRON_TICK_MS.
        let ts = states(&[
            task("a", 15_000, None),
            task("b", 2_000, None),
            task("c", 0, Some("0 */6 * * *")),
        ]);
        assert_eq!(tick_ms_for_tasks(&ts, 5000), 1000);
        let ts = states(&[task("a", 750, None), task("c", 0, Some("* * * * *"))]);
        assert_eq!(tick_ms_for_tasks(&ts, 5000), 250);
        let ts = states(&[task("a", 120_000, None), task("c", 0, Some("* * * * *"))]);
        assert!(tick_ms_for_tasks(&ts, 5000) <= 60_000);
    }

    #[test]
    fn add_task_rejects_invalid_schedule() {
        let mut sched = TaskScheduler::new(100);
        let err = sched
            .add_task(&task("bad-cron", 0, Some("61 * * * *")))
            .unwrap_err();
        assert!(format!("{err:#}").contains("bad-cron"));
        assert!(sched.task_names().is_empty());

        sched
            .add_task(&task("good-cron", 0, Some("*/5 * * * *")))
            .unwrap();
        assert_eq!(sched.task_names(), vec!["good-cron".to_owned()]);
    }

    /// Context that counts reads of `run:<task>` fields (one per task run),
    /// serves `hp` (50 unless set in the map), fails on `broken` and
    /// panics on `boom`.
    type Counts = Arc<Mutex<HashMap<String, u32>>>;
    struct CountCtx(Counts);
    impl ActionContext for CountCtx {
        fn resolve_field(&self, field_name: &str) -> anyhow::Result<Vec<u8>> {
            match field_name {
                "hp" => {
                    let hp = self.0.lock().unwrap().get("hp").copied().unwrap_or(50);
                    Ok(hp.to_le_bytes().to_vec())
                }
                "broken" => anyhow::bail!("read failed"),
                "boom" => panic!("context read panicked"),
                _ => {
                    *self
                        .0
                        .lock()
                        .unwrap()
                        .entry(field_name.to_owned())
                        .or_default() += 1;
                    Ok(0u32.to_le_bytes().to_vec())
                }
            }
        }
    }

    fn count_engine() -> (BotEngine, Counts) {
        let counts = Counts::default();
        let engine = BotEngine::new(
            Box::new(DumpReader),
            Box::new(NoopInput),
            Box::new(CountCtx(Arc::clone(&counts))),
            crate::engine::HookRegistry::new(),
        );
        (engine, counts)
    }

    /// Task whose single action marks one run in [`CountCtx`].
    fn counted(name: &str, interval_ms: u32, schedule: Option<&str>) -> BotTask {
        BotTask {
            actions: vec![BotAction::MemoryCheck {
                field: format!("run:{name}"),
                op: crate::actions::ComparisonOp::GtEq,
                value: crate::actions::ValueSpec::U64(0),
            }],
            ..task(name, interval_ms, schedule)
        }
    }

    fn guard(field: &str) -> BotCondition {
        BotCondition {
            field: field.into(),
            op: crate::actions::ComparisonOp::Lt,
            value: crate::actions::ValueSpec::U64(30),
        }
    }

    fn runs(counts: &Counts, name: &str) -> u32 {
        counts
            .lock()
            .unwrap()
            .get(&format!("run:{name}"))
            .copied()
            .unwrap_or(0)
    }

    fn wall(h: u32, mi: u32, sec: u32) -> chrono::DateTime<chrono::Utc> {
        chrono::Utc
            .with_ymd_and_hms(2026, 10, 26, h, mi, sec)
            .unwrap()
    }

    #[tokio::test]
    async fn interval_task_does_not_run_twice_within_interval() {
        let (engine, counts) = count_engine();
        let mut ts = states(&[counted("a", 1000, None), counted("d", 0, None)]);
        let t0 = Instant::now();
        let w = wall(10, 0, 0);
        tick(&mut ts, true, 5000, &engine, t0, &w).await;
        tick(
            &mut ts,
            true,
            5000,
            &engine,
            t0 + Duration::from_millis(999),
            &w,
        )
        .await;
        assert_eq!(runs(&counts, "a"), 1);
        tick(
            &mut ts,
            true,
            5000,
            &engine,
            t0 + Duration::from_millis(1000),
            &w,
        )
        .await;
        assert_eq!(runs(&counts, "a"), 2);
        // interval_ms = 0 uses the default (5000 ms).
        assert_eq!(runs(&counts, "d"), 1);
        tick(
            &mut ts,
            true,
            5000,
            &engine,
            t0 + Duration::from_millis(5000),
            &w,
        )
        .await;
        assert_eq!(runs(&counts, "d"), 2);
    }

    #[tokio::test]
    async fn cron_task_starts_only_in_matching_minute() {
        let (engine, counts) = count_engine();
        // A 1 ms interval_ms would fire every tick: schedule must win.
        let mut ts = states(&[counted("c", 1, Some("*/15 * * * *"))]);
        let t0 = Instant::now();
        let mut step = 0u64;
        for (h, mi, sec, expect) in [
            (10, 7, 0, 0),
            (10, 15, 0, 1),
            (10, 15, 30, 1), // same minute: no second start
            (10, 16, 0, 1),
            (10, 30, 5, 2),
        ] {
            step += 1;
            let now = t0 + Duration::from_secs(step * 60);
            tick(&mut ts, true, 500, &engine, now, &wall(h, mi, sec)).await;
            assert_eq!(runs(&counts, "c"), expect, "at {h}:{mi}:{sec}");
        }
    }

    #[tokio::test]
    async fn false_or_unreadable_head_condition_skips_only_that_task() {
        let (engine, counts) = count_engine();
        let mut guarded = counted("guarded", 0, None);
        guarded.conditions = vec![guard("hp")]; // hp = 50, needs < 30
        let mut broken = counted("broken", 0, None);
        broken.conditions = vec![guard("broken")]; // read fails
        let mut ts = states(&[guarded, broken, counted("free", 0, None)]);

        tick(&mut ts, true, 500, &engine, Instant::now(), &wall(10, 0, 0)).await;
        assert_eq!(runs(&counts, "guarded"), 0);
        assert_eq!(runs(&counts, "broken"), 0);
        assert_eq!(ts[1].fail_count, 1);
        assert_eq!(runs(&counts, "free"), 1);
    }

    #[tokio::test]
    async fn skipped_task_runs_once_condition_turns_true() {
        let (engine, counts) = count_engine();
        let mut guarded = counted("guarded", 0, None);
        guarded.conditions = vec![guard("hp")];
        let mut ts = states(&[guarded]);
        let t0 = Instant::now();
        let w = wall(10, 0, 0);

        tick(&mut ts, true, 500, &engine, t0, &w).await;
        assert_eq!(runs(&counts, "guarded"), 0);
        counts.lock().unwrap().insert("hp".into(), 10);
        // The skipped start consumed its slot: next start is one interval later.
        tick(
            &mut ts,
            true,
            500,
            &engine,
            t0 + Duration::from_millis(499),
            &w,
        )
        .await;
        assert_eq!(runs(&counts, "guarded"), 0);
        tick(
            &mut ts,
            true,
            500,
            &engine,
            t0 + Duration::from_millis(500),
            &w,
        )
        .await;
        assert_eq!(runs(&counts, "guarded"), 1);
        assert!(ts[0].enabled);
    }

    #[tokio::test]
    async fn stop_interrupts_long_sleep_and_running_tick() {
        // tick_ms = 300 s: stop() must not wait for the sleep to finish.
        let idle = BotConfig {
            tasks: vec![task("idle", 300_000, None)],
            ..BotConfig::default()
        };
        // A task stuck in a 10 min `!Wait` must not block stop() either.
        let mut stuck = task("stuck", 300_000, None);
        stuck.actions = vec![BotAction::Wait { millis: 600_000 }];
        let busy = BotConfig {
            tasks: vec![stuck],
            ..BotConfig::default()
        };
        for cfg in [idle, busy] {
            let (engine, _) = count_engine();
            let sched = TaskScheduler::from_config(&cfg).unwrap();
            sched.start(Arc::new(engine));
            tokio::time::sleep(Duration::from_millis(20)).await;
            tokio::time::timeout(Duration::from_secs(2), sched.stop())
                .await
                .expect("stop() should return promptly")
                .unwrap();
            assert!(!sched.is_running());
        }
    }

    #[tokio::test]
    async fn wait_reports_a_panicked_tick_loop() {
        let (engine, _) = count_engine();
        let mut boom = counted("boom", 0, None);
        boom.conditions = vec![guard("boom")];
        let sched = TaskScheduler::from_config(&BotConfig {
            tasks: vec![boom],
            ..BotConfig::default()
        })
        .unwrap();
        sched.start(Arc::new(engine));
        let err = sched.wait().await.unwrap_err();
        assert!(err.is_panic());
        assert!(!sched.is_running());
    }

    #[tokio::test]
    async fn run_once_ignores_timing_but_applies_conditions() {
        let (engine, counts) = count_engine();
        let mut guarded = counted("guarded", 0, None);
        guarded.conditions = vec![guard("hp")];
        let mut off = counted("off", 0, None);
        off.enabled = false;
        let cfg = BotConfig {
            tasks: vec![counted("cron", 0, Some("0 0 1 1 *")), guarded, off],
            ..BotConfig::default()
        };
        let mut sched = TaskScheduler::from_config(&cfg).unwrap();
        sched.run_once(&engine).await;
        assert_eq!(runs(&counts, "cron"), 1);
        assert_eq!(runs(&counts, "guarded"), 0);
        assert_eq!(runs(&counts, "off"), 0);

        let mut sched = TaskScheduler::from_config(&BotConfig {
            enabled: false,
            ..cfg
        })
        .unwrap();
        sched.run_once(&engine).await;
        assert_eq!(runs(&counts, "cron"), 1);
    }

    #[derive(Default)]
    struct NoopInput;
    impl crate::engine::InputSimulator for NoopInput {}
}
