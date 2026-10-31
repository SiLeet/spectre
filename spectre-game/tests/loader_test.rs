// Integration tests for spectre-game: the loader must parse both YAML
// dialects found in the repo (`type: "u32"` lowercase style and
// `field_type: U32` / `String(32)` CamelCase style) including hex offsets,
// and the registry must answer structure/field/version queries.

use spectre_core::FieldType;
use spectre_game::OffsetLoader;
use spectre_game::registry::{GameRegistry, quick_struct, version_in_range};

fn crate_dir() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

#[test]
fn loads_crate_local_game_file() {
    let dir = crate_dir().join("games");
    let loader = OffsetLoader::from_dir(&dir);
    let all = loader.all();
    assert_eq!(
        all.len(),
        1,
        "expected exactly the crate-local afk-journey.yaml"
    );

    let go = &all[0];
    assert_eq!(go.game, "AFK Journey");
    assert_eq!(go.version, "1.0.0");

    let ps = go
        .structures
        .iter()
        .find(|s| s.name == "PlayerState")
        .expect("PlayerState structure");
    assert_eq!(ps.base_offset, 0);

    let name = ps
        .fields
        .iter()
        .find(|f| f.name == "name")
        .expect("name field");
    assert_eq!(name.field_type, FieldType::String(128));
    assert_eq!(name.offset, 0x1234, "hex offset must parse");

    let level = ps
        .fields
        .iter()
        .find(|f| f.name == "level")
        .expect("level field");
    assert_eq!(level.field_type, FieldType::U32);
    assert_eq!(level.offset, 0x1260);
}

#[test]
fn loads_workspace_game_file() {
    let dir = crate_dir().join("..").join("games").join("afk-journey");
    let loader = OffsetLoader::from_dir(&dir);
    let all = loader.all();
    assert_eq!(all.len(), 1, "expected the workspace offsets.yaml");

    let go = &all[0];
    assert_eq!(go.game, "afk-journey");
    assert_eq!(go.version, "1.0.45");

    let ps = go
        .structures
        .iter()
        .find(|s| s.name == "PlayerState")
        .expect("PlayerState structure");
    assert_eq!(ps.base_offset, 0x1A2B3C00, "hex base offset must parse");

    let nickname = ps
        .fields
        .iter()
        .find(|f| f.name == "nickname")
        .expect("nickname field");
    assert_eq!(
        nickname.field_type,
        FieldType::String(32),
        "String(32) must parse"
    );

    let level = ps
        .fields
        .iter()
        .find(|f| f.name == "level")
        .expect("level field");
    assert_eq!(level.field_type, FieldType::U32, "U32 CamelCase must parse");
}

#[test]
fn default_loader_scans_all_locations() {
    let loader = OffsetLoader::new();
    // CWD/games + <crate>/games + <crate>/../games merge, deduped by (game, version).
    let names: Vec<String> = loader.all().iter().map(|g| g.game.clone()).collect();
    assert!(
        names.iter().any(|n| n == "AFK Journey"),
        "crate-local file loaded: {names:?}"
    );
    assert!(
        names.iter().any(|n| n == "afk-journey"),
        "workspace file loaded: {names:?}"
    );
}

#[test]
fn missing_dir_is_empty_not_error() {
    let loader = OffsetLoader::from_dir("/nonexistent/this/does/not/exist");
    assert!(loader.is_empty());
}

#[test]
fn malformed_file_is_skipped() {
    let dir = std::env::temp_dir().join(format!("spectre_game_bad_{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("bad.yaml"), "game: [unclosed").unwrap();
    std::fs::write(
        dir.join("good.yaml"),
        "game: tmp-game\nversion: 0.1.0\nstructures: []\n",
    )
    .unwrap();

    let loader = OffsetLoader::from_dir(&dir);
    let all = loader.all();
    assert_eq!(all.len(), 1);
    assert_eq!(all[0].game, "tmp-game");

    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn unknown_field_type_field_is_skipped() {
    let dir = std::env::temp_dir().join(format!("spectre_game_ft_{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("weird.yaml"),
        r#"
game: weird
version: 1.0.0
structures:
  - name: S
    base_offset: 0
    fields:
      - name: ok
        type: "u32"
        offset: 0
      - name: bad
        type: "uint128"
        offset: 4
"#,
    )
    .unwrap();

    let loader = OffsetLoader::from_dir(&dir);
    let all = loader.all();
    assert_eq!(all.len(), 1);
    let s = &all[0].structures[0];
    assert_eq!(s.fields.len(), 1, "unknown-type field must be skipped");
    assert_eq!(s.fields[0].name, "ok");

    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn version_semantics() {
    // exact entry version matches only that exact target
    assert!(version_in_range("1.0.0", "1.0.0"));
    assert!(!version_in_range("1.0.0", "1.0.1"));
    assert!(!version_in_range("1.0.0", "0.9.9"));
    // inclusive range
    assert!(version_in_range("1.0.0-2.0.0", "1.0.0"));
    assert!(version_in_range("1.0.0-2.0.0", "1.5.0"));
    assert!(version_in_range("1.0.0-2.0.0", "2.0.0"));
    assert!(!version_in_range("1.0.0-2.0.0", "2.0.1"));
    assert!(!version_in_range("1.0.0-2.0.0", "0.9.0"));
    // spaced range
    assert!(version_in_range("1.0.0 - 2.0.0", "1.2.3"));
    // prerelease-ish exact string is not treated as a range
    assert!(version_in_range("2.0.0-beta", "2.0.0-beta"));
}

#[test]
fn registry_queries() {
    let reg = GameRegistry::scan_dir(&crate_dir().join("games").display().to_string());
    assert_eq!(reg.len(), 1);
    assert_eq!(reg.game_names(), vec!["AFK Journey".to_string()]);

    let ps = reg
        .find_struct("afk journey", "PlayerState")
        .expect("struct lookup");
    assert_eq!(ps.base_offset, 0);

    let exp = reg
        .find_field("AFK Journey", "PlayerState", "exp")
        .expect("field lookup");
    assert_eq!(exp.field_type, FieldType::U32);
    assert_eq!(exp.offset, 0x1264);

    let best = reg.find_best("AFK Journey", "1.0.0").expect("find_best");
    assert_eq!(best.offsets.version, "1.0.0");
    assert!(reg.find_best("AFK Journey", "9.9.9").is_none());

    assert!(
        quick_struct(
            &crate_dir().join("games").display().to_string(),
            "AFK Journey",
            "PlayerState"
        )
        .is_some()
    );
}

#[test]
fn exact_entries_beat_ranges_in_find_best() {
    let mut reg = GameRegistry::with_entries(vec![
        spectre_game::GameEntry {
            offsets: spectre_core::GameOffsets {
                game: "g".into(),
                version: "1.0.0-2.0.0".into(),
                structures: vec![],
            },
            platforms: vec![],
        },
        spectre_game::GameEntry {
            offsets: spectre_core::GameOffsets {
                game: "g".into(),
                version: "1.2.0".into(),
                structures: vec![],
            },
            platforms: vec![],
        },
    ]);
    let best = reg.find_best("g", "1.2.0").expect("best match");
    assert_eq!(
        best.offsets.version, "1.2.0",
        "exact version entry must win over range"
    );
    let _ = &mut reg;
}

// ── Validator ────────────────────────────────────────────────────────────

fn issues_of(yaml: &str) -> Vec<spectre_game::Issue> {
    spectre_game::validate(&serde_yaml::from_str(yaml).expect("test YAML parses"))
}

#[test]
fn validator_finds_duplicate_structure() {
    let issues = issues_of("{game: g, version: '1', structures: [{name: S}, {name: S}]}");
    assert_eq!(issues.len(), 1, "{issues:?}");
    assert_eq!(issues[0].severity, spectre_game::Severity::Error);
    assert_eq!(issues[0].structure.as_deref(), Some("S"));
}

#[test]
fn validator_finds_duplicate_field() {
    let issues = issues_of(
        "{game: g, version: '1', structures: [{name: S, fields: [         {name: a, type: u8, offset: 0}, {name: a, type: u8, offset: 4}]}]}",
    );
    assert_eq!(issues.len(), 1, "{issues:?}");
    assert_eq!(issues[0].field.as_deref(), Some("a"));
    assert_eq!(issues[0].severity, spectre_game::Severity::Error);
}

#[test]
fn validator_warns_on_overlapping_fields() {
    // b (0x4..0x8) and c (0x6..0x7) both overlap a (0x0..0x8); d (0x8) does not.
    let issues = issues_of(
        "{game: g, version: '1', structures: [{name: S, fields: [         {name: a, type: u64, offset: 0}, {name: b, type: u32, offset: 4},          {name: c, type: string, length: 1, offset: 6}, {name: d, type: u8, offset: 8}]}]}",
    );
    let flagged: Vec<_> = issues.iter().map(|i| i.field.as_deref().unwrap()).collect();
    assert_eq!(flagged, ["b", "c"], "{issues:?}");
    assert!(issues.iter().all(|i| i.severity == spectre_game::Severity::Warning));
}

#[test]
fn validator_finds_empty_version_and_unknown_type() {
    let issues = issues_of(
        "{game: g, version: ' ', structures: [{name: S, fields: [{name: a, type: u128, offset: 0}]}]}",
    );
    assert_eq!(issues.len(), 2, "{issues:?}");
    assert!(issues[0].message.contains("version"));
    assert!(issues[1].message.contains("u128"));
    assert!(issues.iter().all(|i| i.severity == spectre_game::Severity::Error));
}

#[test]
fn validator_rejects_zero_length_strings() {
    // A 0-byte range never overlaps, so `a` sharing offset 0 with `d` must
    // still be reported, as an error.
    let issues = issues_of(
        "{game: g, version: '1', structures: [{name: S, fields: [         {name: a, type: 'string:0', offset: 0}, {name: b, type: 'String(0)', offset: 0},          {name: c, type: string, length: 0, offset: 0}, {name: d, type: u32, offset: 0}]}]}",
    );
    let flagged: Vec<_> = issues.iter().map(|i| i.field.as_deref().unwrap()).collect();
    assert_eq!(flagged, ["a", "b", "c"], "{issues:?}");
    assert!(issues.iter().all(|i| i.severity == spectre_game::Severity::Error));
}

#[test]
fn repo_offset_files_have_no_validation_errors() {
    let root = crate_dir().join("..");
    let files_in = |dir: &str, keep: fn(&std::path::Path) -> bool| {
        std::fs::read_dir(root.join(dir))
            .expect(dir)
            .map(|e| e.expect(dir).path())
            .filter(|p| keep(p))
            .collect::<Vec<_>>()
    };
    let is_yaml = |p: &std::path::Path| p.extension().is_some_and(|e| e == "yaml");
    let mut files = files_in("games", |p| p.join("offsets.yaml").is_file());
    files.iter_mut().for_each(|p| p.push("offsets.yaml"));
    files.extend(files_in("examples", |p| {
        p.extension().is_some_and(|e| e == "yaml")
            && p.file_name().unwrap().to_string_lossy().contains("offsets")
    }));
    files.extend(files_in("spectre-game/games", is_yaml));
    assert!(files.len() >= 3, "{files:?}");

    for path in &files {
        let file = spectre_game::offsets::read_yaml_file(path).expect("offsets file parses");
        let errors: Vec<_> = spectre_game::validate(&file)
            .into_iter()
            .filter(|i| i.severity == spectre_game::Severity::Error)
            .collect();
        assert!(errors.is_empty(), "{}: {errors:?}", path.display());
    }
}
