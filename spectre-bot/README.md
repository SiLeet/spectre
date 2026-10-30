# spectre-bot

Game-agnostic bot execution engine for the [Spectre](https://github.com/sergej-dukart/spectre) game-memory analysis framework.

**spectre-bot** provides an action-based scripting system for automating
in-game actions based on game-memory state. Actions reference memory fields
by name, resolved at runtime through a game-specific offset registry.

## Features

- **8 action primitives** — `MemoryCheck`, `InputClick`, `InputSwipe`, `Wait`,
  `Loop`, `Condition`, `ScriptHook`, `Log`
- **Condition system** — Compare memory field values (u64, i64, f64, bytes)
  with operators: `==`, `!=`, `<`, `>`, `<=`, `>=`
- **Composite actions** — `Loop` (finite or infinite), `Condition` (if/else),
  `MemoryCheck` (poll-and-gate)
- **Abstract input backend** — `InputSimulator` trait for ADB, native OS, or
  custom backends
- **Memory field resolution** — `ActionContext` trait bridges field names to
  actual process-memory reads via `spectre-core::MemoryReader`
- **Script hooks** — Register named callable hooks invoked from action trees
- **Task scheduler** — Async timer loop runs tasks at configurable intervals
  with guard-condition checking, pause/resume, and automatic stop on signal
- **YAML configuration** — Full bot scripts serializable as YAML for easy editing

## Architecture

```
┌─────────────────────────────────────────────┐
│                BotConfig (YAML)              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ BotTask  │  │ BotTask  │  │ BotTask  │  │
│  │ actions  │  │ actions  │  │ actions  │  │
│  │ interval │  │ interval │  │ interval │  │
│  │ enabled  │  │ enabled  │  │ enabled  │  │
│  └────┬─────┘  └──────────┘  └──────────┘  │
│       │                                     │
└───────┤─────────────────────────────────────┘
        │
  ┌─────▼──────────────────────┐
  │     TaskScheduler          │  ◀── async timer loop
  │  ┌─ tick() ─────────────┐  │
  │  │  check guards        │  │
  │  │  execute actions ────│──│── BotEngine
  │  └──────────────────────┘  │      │
  └────────────────────────────┘      │
          │              │            │
    ┌─────▼──────┐  ┌────▼─────┐  ┌──▼────────┐
    │ActionContext│  │InputSim │  │HookRegistr│
    │read_field()│  │click()  │  │invoke()   │
    │            │  │swipe()  │  │           │
    └────────────┘  └─────────┘  └───────────┘
```

## Quick Start

### 1. Define a config (YAML)

```yaml
# auto_bot.yaml
default_interval_ms: 500
input_backend: adb
memory_poll_ms: 100
enabled: true
tasks:
  - name: auto_heal
    interval_ms: 300
    enabled: true
    conditions:
      - field_name: player_hp
        op: Lt
        value: !Uint 30
    actions:
      - MemoryCheck:
          field_name: player_hp
          condition:
            field_name: player_hp
            op: Lt
            value: !Uint 30
          actions:
            - InputClick:
                x: 400
                y: 600
                button: left
            - Wait:
                duration_ms: 2000
            - InputClick:
                x: 350
                y: 500
                button: left
      - Log:
          message: Auto-heal triggered
          level: Info
```

### 2. Load and run

```rust
use spectre_bot::{BotConfig, BotEngine, TaskScheduler, HookRegistry};
use spectre_bot::engine::{ActionContext, InputSimulator};

// Load config
let config = BotConfig::from_yaml_file("auto_bot.yaml")?;

// Create engine components
let ctx = MyActionContext::new(reader, offsets);
let input = AdbInputSimulator::new("192.168.1.100", 5555);
let hooks = HookRegistry::new();

// Create engine
let engine = BotEngine::new(&ctx, &input, &hooks);

// Start scheduler
let scheduler = TaskScheduler::new(config.default_interval_ms);
for task in config.tasks {
    scheduler.add_task(task);
}
scheduler.start(&engine, &ctx, &input, &hooks);

// Later: await tokio::signal::shutdown() or call scheduler.stop()
```

## Action Reference

| Action | Fields | Description |
|--------|--------|-------------|
| `MemoryCheck` | `field_name`, `condition`, `actions` | Read memory — run sub-actions only when condition is true |
| `InputClick` | `x`, `y`, `button?` | Click/tap at screen coordinates |
| `InputSwipe` | `x1`, `y1`, `x2`, `y2`, `duration_ms` | Swipe/drag gesture |
| `Wait` | `duration_ms` | Pause execution |
| `Loop` | `count`, `actions` | Repeat actions N times (0 = infinite) |
| `Condition` | `condition`, `then_actions`, `else_actions` | If/else branching |
| `ScriptHook` | `name`, `args` | Call a registered hook |
| `Log` | `message`, `level` | Write a log entry |

## Condition Operators

- `Eq` — field == value
- `Neq` — field != value
- `Lt` — field < value
- `Gt` — field > value
- `Le` — field <= value
- `Ge` — field >= value

## Implementing an Input Backend

```rust
use spectre_bot::engine::InputSimulator;

pub struct AdbSimulator {
    host: String,
    port: u16,
}

impl InputSimulator for AdbSimulator {
    fn tap(&self, x: u32, y: u32) -> anyhow::Result<()> {
        // adb shell input tap {x} {y}
    }
    fn click(&self, x: u32, y: u32, button: &str) -> anyhow::Result<()> {
        // ...
    }
    fn swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, d: u32) -> anyhow::Result<()> {
        // ...
    }
    fn input_text(&self, text: &str) -> anyhow::Result<()> { ... }
    fn key_press(&self, key: &str) -> anyhow::Result<()> { ... }
    fn backend_name(&self) -> String { "adb" }
}
```

## Implementing an ActionContext

```rust
use spectre_bot::engine::ActionContext;

pub struct GameContext {
    reader: &dyn spectre_core::MemoryReader,
    pid: u32,
    offsets: HashMap<String, (u64, u32)>,  // field_name → (address, size)
}

impl ActionContext for GameContext {
    fn read_field(&self, field_name: &str) -> anyhow::Result<Vec<u8>> {
        let (addr, size) = self.offsets.get(field_name)
            .unwrap_or_else(|| anyhow::bail!("unknown field: {}", field_name));
        self.reader.read_bytes(self.pid, addr, size)
    }
    fn backend(&self) -> String { "native" }
}
```

## Dependencies

- `spectre-core` — Memory reader trait and scan types
- `spectre-game` — Game offset registry (optional, for production field resolution)
- `anyhow`, `traced`, `tokio`, `serde`, `serde_yaml`

## License

MIT