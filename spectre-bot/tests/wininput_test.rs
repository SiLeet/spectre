//! Input-backend tests.
//!
//! These tests NEVER generate real OS input: dispatch is verified through a
//! recording mock, and the Windows backend is only constructed, not invoked.
use std::sync::{Arc, Mutex};

use spectre_bot::{
    ActionContext, ActionResult, BotAction, BotEngine, HookRegistry, InputSimulator,
};
use spectre_core::reader::MemoryReader;
use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};

// ── Test doubles ────────────────────────────────────────────────────────────

/// A single recorded input call.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Call {
    Click(u32, u32),
    Swipe(u32, u32, u32, u32, u64),
}

/// In-memory input simulator that records every call instead of sending it.
#[derive(Clone, Default)]
struct RamInputSimulator {
    calls: Arc<Mutex<Vec<Call>>>,
    fail: bool,
}

impl InputSimulator for RamInputSimulator {
    fn click(&self, x: u32, y: u32) -> anyhow::Result<()> {
        self.calls.lock().unwrap().push(Call::Click(x, y));
        if self.fail {
            anyhow::bail!("mock click failure");
        }
        Ok(())
    }

    fn swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, millis: u64) -> anyhow::Result<()> {
        self.calls
            .lock()
            .unwrap()
            .push(Call::Swipe(x1, y1, x2, y2, millis));
        Ok(())
    }
}

struct NoCtx;
impl ActionContext for NoCtx {
    fn resolve_field(&self, field_name: &str) -> anyhow::Result<Vec<u8>> {
        anyhow::bail!("unknown field '{}'", field_name)
    }
}

#[derive(Debug)]
struct NoReader;
impl MemoryReader for NoReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::DumpFile
    }
    fn find_process(&self, _name: &str) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(Vec::new())
    }
    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(Vec::new())
    }
    fn memory_regions(&self, _pid: u32) -> anyhow::Result<Vec<MemoryRegion>> {
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
        _patterns: Vec<ScanPattern>,
        _little: bool,
    ) -> anyhow::Result<Vec<ScanReport>> {
        Ok(Vec::new())
    }
}

fn engine_with(input: RamInputSimulator) -> BotEngine {
    BotEngine::new(
        Box::new(NoReader),
        Box::new(input),
        Box::new(NoCtx),
        HookRegistry::new(),
    )
}

// ── Dispatch tests ──────────────────────────────────────────────────────────

#[tokio::test]
async fn run_action_dispatches_click_to_input() {
    let input = RamInputSimulator::default();
    let engine = engine_with(input.clone());

    let result = engine
        .run_action(BotAction::InputClick { x: 120, y: 340 })
        .await;

    assert_eq!(result, ActionResult::Ok);
    assert_eq!(*input.calls.lock().unwrap(), vec![Call::Click(120, 340)]);
}

#[tokio::test]
async fn run_action_dispatches_swipe_to_input() {
    let input = RamInputSimulator::default();
    let engine = engine_with(input.clone());

    let result = engine
        .run_action(BotAction::InputSwipe {
            x1: 1,
            y1: 2,
            x2: 3,
            y2: 4,
            millis: 250,
        })
        .await;

    assert_eq!(result, ActionResult::Ok);
    assert_eq!(
        *input.calls.lock().unwrap(),
        vec![Call::Swipe(1, 2, 3, 4, 250)]
    );
}

#[tokio::test]
async fn input_error_becomes_action_error() {
    let input = RamInputSimulator {
        fail: true,
        ..Default::default()
    };
    let engine = engine_with(input.clone());

    let result = engine
        .run_action(BotAction::InputClick { x: 5, y: 6 })
        .await;

    assert!(result.is_error(), "expected error, got {:?}", result);
    assert_eq!(*input.calls.lock().unwrap(), vec![Call::Click(5, 6)]);
}

// ── Windows backend (construction only) ─────────────────────────────────────

#[cfg(windows)]
#[test]
fn windows_input_is_constructible_and_send_sync() {
    fn assert_send_sync<T: Send + Sync>() {}
    assert_send_sync::<spectre_bot::WindowsInput>();

    // Plugs into the engine like any other backend — but is never invoked here.
    let _engine = BotEngine::new(
        Box::new(NoReader),
        Box::new(spectre_bot::WindowsInput::new()),
        Box::new(NoCtx),
        HookRegistry::new(),
    );
}
