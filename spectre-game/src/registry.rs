// ── Spectre Game: Game Registry ──────────────────────────────────────────
//
// Central registry for looking up game offset definitions loaded from YAML.
// Supports multiple games, version ranges, and structure/field queries.

use spectre_core::{FieldDef, GameOffsets, StructDef};

use crate::offsets::{LoadedOffsets, OffsetLoader};

// ── Version range helpers ────────────────────────────────────────────────

fn looks_like_version(s: &str) -> bool {
    s.chars().next().is_some_and(|c| c.is_ascii_digit())
}

/// Try to split a version field into `(low, high)`.
/// Accepts: `"1.0.0"`, `"1.0.0-2.0.0"`, `"1.0.0 - 2.0.0"`.
fn parse_version_range(version: &str) -> (String, Option<String>) {
    let s = version.trim();

    if let Some(idx) = s.find(" - ") {
        let low = s[..idx].trim();
        let high = s[idx + 3..].trim();
        if looks_like_version(low) && looks_like_version(high) {
            return (low.to_string(), Some(high.to_string()));
        }
    }

    if let Some(idx) = s.find('-') {
        let low = s[..idx].trim();
        let high = s[idx + 1..].trim();
        if idx > 0 && !high.is_empty() && looks_like_version(low) && looks_like_version(high) {
            return (low.to_string(), Some(high.to_string()));
        }
    }

    (s.to_string(), None)
}

/// Simple three-component version (major.minor.patch).  Components that
/// fail to parse are treated as 0; extra components are ignored.
fn parse_semver(s: &str) -> (u64, u64, u64) {
    let mut parts = s.trim().split('.');
    let maj = parts
        .next()
        .and_then(|p| p.trim().parse().ok())
        .unwrap_or(0);
    let min = parts
        .next()
        .and_then(|p| p.trim().parse().ok())
        .unwrap_or(0);
    let pat = parts
        .next()
        .and_then(|p| p.trim().parse().ok())
        .unwrap_or(0);
    (maj, min, pat)
}

/// Check whether `target_version` (an actual game version string) falls
/// within the version declared in a `GameOffsets` entry: an exact version
/// string (`"1.0.0"`) matches only that exact version, while a range
/// (`"1.0.0-2.0.0"`) matches inclusively.
pub fn version_in_range(entry_version: &str, target_version: &str) -> bool {
    let (low, high) = parse_version_range(entry_version);
    let target = parse_semver(target_version);

    let Some(high) = high else {
        return parse_semver(&low) == target;
    };

    let low = parse_semver(&low);
    let high = parse_semver(&high);
    target >= low && target <= high
}

/// `(is_range, span)` used to rank entries for `find_best`: exact versions
/// sort before ranges, and among ranges the narrower span sorts first.
fn specificity_score(version: &str) -> (u8, u64) {
    let (low, high) = parse_version_range(version);
    match high {
        None => (0, 0),
        Some(high) => {
            let lv = parse_semver(&low);
            let hv = parse_semver(&high);
            let span = hv.0.saturating_sub(lv.0) * 1_000_000
                + hv.1.saturating_sub(lv.1) * 1_000
                + hv.2.saturating_sub(lv.2);
            (1, span)
        }
    }
}

// ── Registry ─────────────────────────────────────────────────────────────

/// A loaded entry in the game registry — core offset data plus any extra
/// metadata from the YAML file.
#[derive(Debug, Clone)]
pub struct GameEntry {
    /// Core offset data.
    pub offsets: GameOffsets,
    /// Target platforms from the YAML file (kept for reference).
    pub platforms: Vec<String>,
}

impl From<LoadedOffsets> for GameEntry {
    fn from(loaded: LoadedOffsets) -> Self {
        GameEntry {
            offsets: loaded.offsets,
            platforms: loaded.platforms,
        }
    }
}

/// Central game offset registry.
///
/// ```
/// # use spectre_game::GameRegistry;
/// let reg = GameRegistry::scan_default();
/// let ps  = reg.find_struct("afk-journey", "PlayerState");
/// ```
pub struct GameRegistry {
    entries: Vec<GameEntry>,
}

impl GameRegistry {
    /// Build an empty registry.
    pub fn new() -> GameRegistry {
        GameRegistry {
            entries: Vec::new(),
        }
    }

    /// Scan a directory and load all game-offset YAML files into the
    /// registry.  Replaces any previously loaded entries.
    pub fn scan_dir(path: &str) -> GameRegistry {
        GameRegistry::from_loader(&OffsetLoader::from_dir(path))
    }

    /// Scan the default `games/` locations (CWD- and crate-relative).
    pub fn scan_default() -> GameRegistry {
        GameRegistry::from_loader(&OffsetLoader::new())
    }

    /// Load entries from a pre-populated `OffsetLoader`.
    pub fn from_loader(loader: &OffsetLoader) -> GameRegistry {
        GameRegistry {
            entries: loader.loaded().into_iter().map(GameEntry::from).collect(),
        }
    }

    /// Replace the registry contents with explicit entries (useful for tests).
    pub fn with_entries(entries: Vec<GameEntry>) -> GameRegistry {
        GameRegistry { entries }
    }

    /// Directly add a single game entry.
    pub fn add(&mut self, entry: GameEntry) {
        self.entries.push(entry);
    }

    // ── Queries ───────────────────────────────────────────────────────

    /// Return all entries.
    pub fn all(&self) -> Vec<GameEntry> {
        self.entries.clone()
    }

    /// Find all game entries whose name matches (case-insensitive).
    pub fn find_game(&self, name: &str) -> Vec<GameEntry> {
        self.entries
            .iter()
            .filter(|e| e.offsets.game.eq_ignore_ascii_case(name))
            .cloned()
            .collect()
    }

    /// Find game entries matching name AND a specific version.
    pub fn find_game_version(&self, name: &str, version: &str) -> Vec<GameEntry> {
        self.entries
            .iter()
            .filter(|e| {
                e.offsets.game.eq_ignore_ascii_case(name)
                    && version_in_range(&e.offsets.version, version)
            })
            .cloned()
            .collect()
    }

    /// Find the best-matching game entry for a version: exact version
    /// entries win; among version ranges the narrowest one wins.
    pub fn find_best(&self, name: &str, version: &str) -> Option<GameEntry> {
        self.entries
            .iter()
            .filter(|e| {
                e.offsets.game.eq_ignore_ascii_case(name)
                    && version_in_range(&e.offsets.version, version)
            })
            .min_by_key(|e| specificity_score(&e.offsets.version))
            .cloned()
    }

    /// Find a structure by game name and structure name.
    pub fn find_struct(&self, game: &str, struct_name: &str) -> Option<StructDef> {
        self.entries
            .iter()
            .filter(|e| e.offsets.game.eq_ignore_ascii_case(game))
            .flat_map(|e| e.offsets.structures.iter())
            .find(|s| s.name == struct_name)
            .cloned()
    }

    /// Find a field by game name, structure name, and field name.
    pub fn find_field(&self, game: &str, struct_name: &str, field_name: &str) -> Option<FieldDef> {
        let sd = self.find_struct(game, struct_name)?;
        sd.fields.into_iter().find(|f| f.name == field_name)
    }

    /// Find a structure within a specific game version.
    pub fn find_struct_version(
        &self,
        game: &str,
        version: &str,
        struct_name: &str,
    ) -> Option<StructDef> {
        self.entries
            .iter()
            .filter(|e| {
                e.offsets.game.eq_ignore_ascii_case(game)
                    && version_in_range(&e.offsets.version, version)
            })
            .flat_map(|e| e.offsets.structures.iter())
            .find(|s| s.name == struct_name)
            .cloned()
    }

    /// Find a field within a specific game version.
    pub fn find_field_version(
        &self,
        game: &str,
        version: &str,
        struct_name: &str,
        field_name: &str,
    ) -> Option<FieldDef> {
        let sd = self.find_struct_version(game, version, struct_name)?;
        sd.fields.into_iter().find(|f| f.name == field_name)
    }

    /// List all known game names in the registry.
    pub fn game_names(&self) -> Vec<String> {
        let mut seen: Vec<String> = Vec::new();
        for e in &self.entries {
            let name = e.offsets.game.clone();
            if !seen.iter().any(|n| n.eq_ignore_ascii_case(&name)) {
                seen.push(name);
            }
        }
        seen
    }

    /// List all structure names for a given game.
    pub fn struct_names(&self, game: &str) -> Vec<String> {
        let mut names: Vec<String> = Vec::new();
        for entry in &self.entries {
            if !entry.offsets.game.eq_ignore_ascii_case(game) {
                continue;
            }
            for sd in &entry.offsets.structures {
                if !names.contains(&sd.name) {
                    names.push(sd.name.clone());
                }
            }
        }
        names
    }

    /// Total number of game entries.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Is the registry empty?
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Remove all entries.
    pub fn clear(&mut self) {
        self.entries.clear();
    }
}

impl Default for GameRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ── Convenience helpers ──────────────────────────────────────────────────

/// Shorthand: load a directory and query one structure.
pub fn quick_struct(games_dir: &str, game: &str, struct_name: &str) -> Option<StructDef> {
    GameRegistry::scan_dir(games_dir).find_struct(game, struct_name)
}
