// ── Spectre Game: Offset File Loader ─────────────────────────────────────
//
// Scans `games/` directories for `.yaml`/`.yml` game-offset definition
// files, deserializes them with serde_yaml, and converts them into core
// `GameOffsets` values.  Missing directories are not an error; malformed
// files are skipped with a warning.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use serde::{Deserialize, Deserializer, Serialize};
use spectre_core::{FieldDef, FieldType, GameOffsets, StructDef};
use tracing::{debug, warn};

// ── YAML entry types (serde-friendly mirrors of the core types) ──────────

/// Top-level structure of a single game-offset YAML file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct YamlGameFile {
    pub game: String,
    /// Single semver like `"1.0.0"` or range like `"1.0.0-2.0.0"`.
    pub version: String,
    #[serde(default)]
    pub platforms: Vec<String>,
    #[serde(default)]
    pub structures: Vec<YamlStructDef>,
}

/// One known structure within a game, defined at a base offset.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct YamlStructDef {
    pub name: String,
    #[serde(default, deserialize_with = "de_u64_flex")]
    pub base_offset: u64,
    #[serde(default)]
    pub fields: Vec<YamlFieldDef>,
}

/// A single field at a specific offset within a structure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct YamlFieldDef {
    pub name: String,
    /// Type string: `u8`..`u64`, `i8`..`i64`, `f32`, `f64`, `bool`,
    /// `string` / `string:N`, `pointer32`, `pointer64`.  Accepted under the
    /// keys `type` and `field_type`, and in lowercase (`u32`) or CamelCase
    /// (`U32`, `String(32)`) spelling.
    #[serde(rename = "field_type", alias = "type")]
    pub field_type: String,
    /// Offset from the structure's base address (hex or decimal in YAML).
    #[serde(deserialize_with = "de_u64_flex")]
    pub offset: u64,
    /// Optional human-readable description.
    #[serde(default)]
    pub desc: Option<String>,
    /// Optional byte length of a string field (overrides `string`'s default
    /// of 128); the same key the CLI's `--offsets` loader accepts.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub length: Option<u32>,
}

/// Deserialize a `u64` from either a YAML integer or a string in decimal or
/// `0x` hex form.  serde_yaml may surface a bare `0x1A2B3C00` scalar as an
/// integer or as a string depending on the loader, so both are accepted.
fn de_u64_flex<'de, D>(d: D) -> Result<u64, D::Error>
where
    D: Deserializer<'de>,
{
    struct FlexVisitor;

    impl serde::de::Visitor<'_> for FlexVisitor {
        type Value = u64;

        fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            f.write_str("an integer or a decimal/hex string")
        }

        fn visit_u64<E>(self, v: u64) -> Result<Self::Value, E>
        where
            E: serde::de::Error,
        {
            Ok(v)
        }

        fn visit_i64<E>(self, v: i64) -> Result<Self::Value, E>
        where
            E: serde::de::Error,
        {
            u64::try_from(v).map_err(|_| E::custom("negative value for u64 field"))
        }

        fn visit_str<E>(self, s: &str) -> Result<Self::Value, E>
        where
            E: serde::de::Error,
        {
            let s = s.trim();
            if let Some(hex) = s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
                u64::from_str_radix(hex, 16)
                    .map_err(|e| E::custom(format!("invalid hex value: {e}")))
            } else {
                s.parse::<u64>()
                    .map_err(|e| E::custom(format!("invalid value: {e}")))
            }
        }
    }

    d.deserialize_any(FlexVisitor)
}

// ── Type conversion helpers ──────────────────────────────────────────────

/// Parse a YAML type string into a core `FieldType`.
///
/// Accepted spellings: lowercase (`u32`, `string`, `string:64`) and the
/// CamelCase YAML variants (`U32`, `String`, `String(32)`).
fn parse_field_type(raw: &str) -> Option<FieldType> {
    let s = raw
        .trim()
        .to_ascii_lowercase()
        .replace('(', ":")
        .replace(')', "");

    if let Some(rest) = s.strip_prefix("string:") {
        let len = rest.trim().parse::<u32>().ok()?;
        return Some(FieldType::String(len));
    }

    match s.as_str() {
        "u8" => Some(FieldType::U8),
        "u16" => Some(FieldType::U16),
        "u32" => Some(FieldType::U32),
        "u64" => Some(FieldType::U64),
        "i8" => Some(FieldType::I8),
        "i16" => Some(FieldType::I16),
        "i32" => Some(FieldType::I32),
        "i64" => Some(FieldType::I64),
        "f32" => Some(FieldType::F32),
        "f64" => Some(FieldType::F64),
        "bool" => Some(FieldType::Bool),
        "string" => Some(FieldType::String(128)),
        "pointer32" | "ptr32" => Some(FieldType::Pointer32),
        "pointer64" | "ptr64" | "pointer" => Some(FieldType::Pointer64),
        _ => None,
    }
}

/// The core type of a YAML field: its type string plus an optional `length`
/// for strings.  `None` if the type string is unknown.
pub(crate) fn resolve_field_type(yf: &YamlFieldDef) -> Option<FieldType> {
    match (parse_field_type(&yf.field_type)?, yf.length) {
        (FieldType::String(_), Some(n)) => Some(FieldType::String(n)),
        (ft, _) => Some(ft),
    }
}

fn to_field_def(yf: &YamlFieldDef) -> Option<FieldDef> {
    let field_type = match resolve_field_type(yf) {
        Some(ft) => ft,
        None => {
            warn!(
                field = %yf.field_type,
                struct_field = %yf.name,
                "Unknown field type; skipping field",
            );
            return None;
        }
    };
    Some(FieldDef {
        name: yf.name.clone(),
        field_type,
        offset: yf.offset,
        desc: yf.desc.clone(),
    })
}

fn to_struct_def(ys: &YamlStructDef) -> StructDef {
    StructDef {
        name: ys.name.clone(),
        base_offset: ys.base_offset,
        fields: ys.fields.iter().filter_map(to_field_def).collect(),
    }
}

// ── OffsetLoader ─────────────────────────────────────────────────────────

/// A loaded offsets file together with non-core metadata from the YAML.
#[derive(Debug, Clone)]
pub struct LoadedOffsets {
    pub offsets: GameOffsets,
    pub platforms: Vec<String>,
}

impl From<YamlGameFile> for LoadedOffsets {
    fn from(yf: YamlGameFile) -> Self {
        let structures = yf.structures.iter().map(to_struct_def).collect();
        LoadedOffsets {
            offsets: GameOffsets {
                game: yf.game,
                version: yf.version,
                structures,
            },
            platforms: yf.platforms,
        }
    }
}

/// Read and deserialize a single YAML offsets file without converting it,
/// e.g. to inspect or [`validate`](crate::validate::validate) it.
pub fn read_yaml_file(path: impl AsRef<Path>) -> Result<YamlGameFile> {
    let path = path.as_ref();
    let text =
        fs::read_to_string(path).with_context(|| format!("failed to read {}", path.display()))?;
    serde_yaml::from_str(&text).with_context(|| format!("failed to parse {}", path.display()))
}

/// Load and convert a single YAML offsets file into core types.
pub fn load_file(path: impl AsRef<Path>) -> Result<LoadedOffsets> {
    Ok(read_yaml_file(path)?.into())
}

/// Candidate `games/` directories: relative to the CWD, the crate dir, and
/// one level above the crate dir.
fn default_locations() -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        dirs.push(cwd.join("games"));
    }
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    dirs.push(manifest.join("games"));
    if let Some(parent) = manifest.parent() {
        dirs.push(parent.join("games"));
    }
    dirs
}

fn collect_yaml_files(dir: &Path) -> Option<Vec<PathBuf>> {
    let mut files = Vec::new();
    walk_yaml_files(dir, &mut files)?;
    files.sort();
    Some(files)
}

/// Recursively collect every `*.yaml` / `*.yml` under `dir`, descending into
/// subdirectories so both `games/<game>.yaml` and `games/<game>/offsets.yaml`
/// layouts are found.  Returns `None` if the root directory is missing.
fn walk_yaml_files(dir: &Path, out: &mut Vec<PathBuf>) -> Option<()> {
    let rd = fs::read_dir(dir).ok()?;
    for entry in rd.flatten() {
        let path = entry.path();
        if path.is_dir() {
            walk_yaml_files(&path, out);
        } else if path.is_file() {
            let lower = path
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            if lower.ends_with(".yaml") || lower.ends_with(".yml") {
                out.push(path);
            }
        }
    }
    Some(())
}

/// Loads and caches game-offset YAML files from `games/` directories.
///
/// Default locations (scanned in order, results merged and deduplicated by
/// `(game, version)`):
///   * `<cwd>/games`
///   * `<crate dir>/games`
///   * `<crate dir>/../games`
///
/// Missing directories are not an error.  Malformed files and fields with
/// unknown types are skipped with a `tracing::warn` rather than failing.
pub struct OffsetLoader {
    entries: Vec<LoadedOffsets>,
}

impl OffsetLoader {
    /// Scan the default `games/` locations.
    pub fn new() -> Self {
        Self::from_dirs(default_locations())
    }

    /// Scan a single explicit directory.  A missing directory yields an
    /// empty loader (no error).
    pub fn from_dir(path: impl AsRef<Path>) -> Self {
        Self::from_dirs(vec![path.as_ref().to_path_buf()])
    }

    fn from_dirs(dirs: Vec<PathBuf>) -> Self {
        let mut entries: Vec<LoadedOffsets> = Vec::new();
        let mut seen: HashSet<(String, String)> = HashSet::new();

        for dir in dirs {
            let Some(files) = collect_yaml_files(&dir) else {
                debug!(dir = %dir.display(), "games directory not found; skipping");
                continue;
            };
            for file in files {
                match load_file(&file) {
                    Ok(loaded) => {
                        let key = (loaded.offsets.game.clone(), loaded.offsets.version.clone());
                        if seen.insert(key) {
                            entries.push(loaded);
                        }
                    }
                    Err(err) => {
                        warn!(file = %file.display(), error = %err, "Skipping malformed offsets file");
                    }
                }
            }
        }

        entries.sort_by(|a, b| {
            a.offsets
                .game
                .cmp(&b.offsets.game)
                .then_with(|| a.offsets.version.cmp(&b.offsets.version))
        });

        Self { entries }
    }

    /// All loaded offsets as core `GameOffsets` values.
    pub fn all(&self) -> Vec<GameOffsets> {
        self.entries.iter().map(|e| e.offsets.clone()).collect()
    }

    /// All loaded entries including YAML metadata (platforms).
    pub fn loaded(&self) -> Vec<LoadedOffsets> {
        self.entries.clone()
    }

    /// Number of loaded game entries.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Clear the cache.
    pub fn clear(&mut self) {
        self.entries.clear();
    }
}

impl Default for OffsetLoader {
    fn default() -> Self {
        Self::new()
    }
}
