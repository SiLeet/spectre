/// Spectre Core — type definitions for game process memory analysis.

// ── Process Info ─────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
}

// ── Memory Regions ───────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct MemoryRegion {
    pub start: u64,
    pub end: u64,
    pub perms: String,
    pub path: Option<String>,
}

impl MemoryRegion {
    pub fn size(&self) -> u64 {
        self.end.saturating_sub(self.start)
    }
}

// ── Endianness ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Endianness {
    Little,
    Big,
}

// ── Value Types ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ValueType {
    U8,
    U16,
    U32,
    U64,
    I8,
    I16,
    I32,
    I64,
    F32,
    F64,
    Bytes(u32),
}

impl ValueType {
    pub fn size(&self) -> u32 {
        match self {
            Self::U8 | Self::I8 => 1,
            Self::U16 | Self::I16 => 2,
            Self::U32 | Self::I32 | Self::F32 => 4,
            Self::U64 | Self::I64 | Self::F64 => 8,
            Self::Bytes(n) => *n,
        }
    }
}

// ── Scan Primitives ──────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum ScanValue {
    Exact(Vec<u8>),
    IntRange(i64, i64),
    FloatRange(f64, f64),
    Any,
}

/// One field in a compound scan pattern.
#[derive(Debug, Clone)]
pub struct PatternField {
    pub name: String,
    pub value_type: ValueType,
    pub value: ScanValue,
    pub alignment: u32,
}

/// A named pattern to locate known structures in memory.
#[derive(Debug, Clone)]
pub struct ScanPattern {
    pub name: String,
    pub fields: Vec<PatternField>,
}

impl ScanPattern {
    /// Total byte span of the pattern including alignment padding.
    pub fn span(&self) -> u64 {
        let mut end: u64 = 0;
        for f in &self.fields {
            let align = u64::max(1, f.alignment as u64);
            end = end.div_ceil(align) * align + f.value_type.size() as u64;
        }
        end
    }
}

/// A single matched occurrence of a pattern.
#[derive(Debug, Clone)]
pub struct ScanMatch {
    pub address: u64,
    pub fields: Vec<(u32, String, Vec<u8>)>,
}

/// Complete scan report for one pattern.
#[derive(Debug, Clone)]
pub struct ScanReport {
    pub pattern_name: String,
    pub matches: Vec<ScanMatch>,
}

// ── Known Structure Descriptors ──────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FieldType {
    U8,
    U16,
    U32,
    U64,
    I8,
    I16,
    I32,
    I64,
    F32,
    F64,
    Bool,
    String(u32),
    Pointer32,
    Pointer64,
}

/// A single named field inside a game-structure offset file.
#[derive(Debug, Clone)]
pub struct FieldDef {
    pub name: String,
    pub field_type: FieldType,
    pub offset: u64,
    pub desc: Option<String>,
}

/// A known structure layout (e.g. "PlayerState") at a base offset.
#[derive(Debug, Clone)]
pub struct StructDef {
    pub name: String,
    pub base_offset: u64,
    pub fields: Vec<FieldDef>,
}

// ── Backends ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackendKind {
    Adb,
    NativeWindows,
    NativeLinux,
    DumpFile,
}

/// Unified handle for a process (host or emulator guest).
#[derive(Debug, Clone)]
pub struct ProcessHandle {
    pub backend: BackendKind,
    pub pid: u32,
    pub name: String,
}

// ── Config ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct AdbConfig {
    pub host: String,
    pub port: u16,
}

impl AdbConfig {
    pub fn localhost() -> Self {
        Self { host: "localhost".to_owned(), port: 5555 }
    }
}

impl Default for AdbConfig {
    fn default() -> Self {
        Self::localhost()
    }
}

#[derive(Debug, Clone)]
pub struct NativeConfig {
    pub process_name: Option<String>,
    pub pid: Option<u32>,
}

/// Top-level configuration for a spectre session.
#[derive(Debug, Clone)]
pub struct SpectreConfig {
    pub backend: BackendKind,
    pub adb: Option<AdbConfig>,
    pub native: Option<NativeConfig>,
    pub game: Option<String>,
}

/// Game-specific offset information (loaded from YAML).
#[derive(Debug, Clone)]
pub struct GameOffsets {
    pub game: String,
    pub version: String,
    pub structures: Vec<StructDef>,
}