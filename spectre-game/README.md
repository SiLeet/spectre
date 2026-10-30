# Spectre Game — Game Offset Registry

Loads YAML-based memory offset definitions for multiple games, versions, and
platforms.  Provides a queryable registry for looking up known structures and
fields by name.

## Why

Memory scanning tools (like Spectre) need to know *where* in a game process's
memory to find specific data — player names, health, coordinates.  This crate
provides the data model and loader for those offset definitions, keeping them
as human-editable YAML files separate from the scanning engine.

## YAML Format

Each file defines one game version (or version range):

```yaml
game: "AFK Journey"
version: "1.0.0"
platforms: ["bluestacks", "android"]
structures:
  - name: "PlayerState"
    base_offset: 0x0
    fields:
      - name: "name"
        type: "string"
        offset: 0x1234
        desc: "Player display name"
      - name: "level"
        type: "u32"
        offset: 0x1260
      - name: "is_online"
        type: "bool"
        offset: 0x1264
      - name: "position"
        type: "f32"
        offset: 0x1270
        desc: "X coordinate"
```

### Field Types

| YAML type      | Core FieldType        | Notes                        |
|----------------|-----------------------|------------------------------|
| `u8` / `u16` / `u32` / `u64` | U8 / U16 / U32 / U64 | Unsigned integers            |
| `i8` / `i16` / `i32` / `i64` | I8 / I16 / I32 / I64 | Signed integers              |
| `f32` / `f64`  | F32 / F64             | IEEE-754 floats              |
| `bool`         | Bool                  | Single byte boolean          |
| `string`       | String(128)           | Null-terminated, default cap |
| `string:64`    | String(64)            | Inline max-length             |
| `pointer32` / `ptr32` | Pointer32        | 32-bit pointer               |
| `pointer64` / `ptr64` / `pointer` | Pointer64 | 64-bit pointer               |

### Version Ranges

The `version` field accepts either an exact semver (`"1.0.0"`) or a range
(`"1.0.0-2.0.0"`).  When multiple entries match a query, `find_best` picks
the narrowest match.

```yaml
# Exact version
game: "AFK Journey"
version: "1.0.0"

# Version range (applies to any version in [1.0.0, 2.0.0))
game: "AFK Journey"
version: "1.0.0-2.0.0"
```

## Usage

```rust
use spectre_game::{GameRegistry, GameEntry};

// Load all YAML files from a directory
let reg = GameRegistry::scan_dir("games/");

// Look up a structure
let ps = reg.find_struct("AFK Journey", "PlayerState");
if ps.is_some() {
    println!("PlayerState at base offset {:#x}", ps.expect().base_offset);
}

// Look up a field (with version awareness)
let field = reg.find_field_version(
    "AFK Journey", "1.0.0", "PlayerState", "name"
);

// List everything available
for game in reg.game_names() {
    for struct_name in reg.struct_names(game) {
        println!("  {}::{}", game, struct_name);
    }
}
```

## Directory Layout

```
spectre-game/
├── src/
│   ├── lib.rs        — Crate root, re-exports
│   ├── offsets.rs    — YAML file loading & deserialization
│   └── registry.rs   — In-memory registry & lookup queries
├── games/            — Example offset YAML files (user-provided)
│   └── afk-journey.yaml
├── Cargo.toml
└── README.md
```

## API Overview

### OffsetLoader (`spectre_game::offsets`)

| Method        | Description                                |
|---------------|--------------------------------------------|
| `new(path)`   | Create loader for a directory              |
| `scan()`      | Read & parse all YAML files, return list   |
| `all()`       | Previously loaded entries                  |
| `clear()`     | Drop cached entries                        |

### GameRegistry (`spectre_game::registry`)

| Method                       | Description                                   |
|------------------------------|-----------------------------------------------|
| `scan_dir(path)`             | Build registry from YAML directory            |
| `from_loader(loader)`        | Build from an existing OffsetLoader           |
| `find_game(name)`            | All entries matching game name                |
| `find_game_version(n, v)`    | Entries matching name + version range         |
| `find_best(name, version)`   | Single best match for name + version          |
| `find_struct(game, struct)`  | First matching structure                      |
| `find_field(g, s, f)`        | First matching field                          |
| `find_struct_version(...)`   | Structure with version filter                 |
| `find_field_version(...)`    | Field with version filter                     |
| `game_names()`               | Deduplicated game names                       |
| `struct_names(game)`         | Structure names for a game                    |

## Dependencies

- `spectre-core` — core type definitions (`FieldDef`, `StructDef`, `FieldType`, `GameOffsets`)
- `serde` + `serde_yaml` — YAML deserialisation
- `anyhow` — error handling conventions