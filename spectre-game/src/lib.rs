// ── Spectre Game ──────────────────────────────────────────────────────────
//
// Game-specific memory offset registry: loads YAML offset definition files,
// and provides a queryable registry for looking up structures and fields by
// game name, version, and field name.

pub mod offsets;
pub mod registry;

pub use offsets::{LoadedOffsets, OffsetLoader, YamlFieldDef, YamlGameFile, YamlStructDef};
pub use registry::{GameEntry, GameRegistry, quick_struct, version_in_range};

// ── Re-exports from spectre-core ─────────────────────────────────────────
//
// Re-export the core types so that consumers of `spectre-game` don't always
// need a direct dependency on `spectre-core`.

pub use spectre_core::FieldDef as CoreFieldDef;
pub use spectre_core::FieldType as CoreFieldType;
pub use spectre_core::GameOffsets as CoreGameOffsets;
pub use spectre_core::StructDef as CoreStructDef;
