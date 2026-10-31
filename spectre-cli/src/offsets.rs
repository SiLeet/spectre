//! `spectre offsets [game]` — list the installed games, or show one game's
//! offsets YAML as a table and validate it (see `spectre_game::validate`).

use std::path::Path;

use anyhow::{Result, anyhow, bail};
use structopt::StructOpt;

use spectre_game::offsets::read_yaml_file;
use spectre_game::{Severity, YamlGameFile, validate};

/// `spectre offsets [game] [--json]`
#[derive(StructOpt)]
pub struct OffsetsArgs {
    /// Game name (games/<game>/offsets.yaml, games/<game>.yaml or .yml), a
    /// name as listed by `spectre offsets`, or a path to an offsets YAML
    /// file. Omit to list the available games.
    #[structopt(name = "game")]
    pub game: Option<String>,

    /// Output as JSON.
    #[structopt(long = "json")]
    pub json: bool,
}

pub fn run_offsets(args: OffsetsArgs) -> Result<()> {
    let Some(game) = args.game else {
        let games = crate::list_installed_games();
        if args.json {
            println!("{}", serde_json::to_string_pretty(&games)?);
        } else if games.is_empty() {
            println!("(none found — place offset YAML files in games/<game>/offsets.yaml)");
        } else {
            for g in &games {
                println!("{g}");
            }
        }
        return Ok(());
    };

    let candidates = [
        format!("games/{game}/offsets.yaml"),
        format!("games/{game}.yaml"),
        format!("games/{game}.yml"),
        format!("games/{game}"),
        game.clone(),
    ];
    let path = candidates
        .iter()
        .find(|p| Path::new(p).is_file())
        .cloned()
        .ok_or_else(|| {
            anyhow!(
                "no offsets file for '{game}' (looked for {})",
                candidates.join(", ")
            )
        })?;

    let file = read_yaml_file(&path)?;
    let issues = validate(&file);

    if args.json {
        let value = serde_json::json!({ "path": path, "offsets": file, "issues": issues });
        println!("{}", serde_json::to_string_pretty(&value)?);
    } else {
        print_table(&path, &file);
        println!();
        if issues.is_empty() {
            println!("validation: ok");
        } else {
            println!("validation: {} issue(s)", issues.len());
            for i in &issues {
                let place = match (&i.structure, &i.field) {
                    (Some(s), Some(f)) => format!("{s}.{f}: "),
                    (Some(s), None) => format!("{s}: "),
                    _ => String::new(),
                };
                let level = match i.severity {
                    Severity::Error => "error",
                    Severity::Warning => "warning",
                };
                println!("  {level}: {place}{}", i.message);
            }
        }
    }

    let errors = issues
        .iter()
        .filter(|i| i.severity == Severity::Error)
        .count();
    if errors > 0 {
        bail!("{path}: {errors} validation error(s)");
    }
    Ok(())
}

fn print_table(path: &str, file: &YamlGameFile) {
    println!("{} v{}  ({path})", file.game, file.version);
    println!();

    let rows: Vec<[String; 5]> = file
        .structures
        .iter()
        .flat_map(|sd| {
            sd.fields.iter().map(move |f| {
                let ty = match f.length {
                    Some(n) => format!("{} (length {n})", f.field_type),
                    None => f.field_type.clone(),
                };
                [
                    format!("{} @ {:#x}", sd.name, sd.base_offset),
                    f.name.clone(),
                    ty,
                    format!("{:#x}", f.offset),
                    f.desc.clone().unwrap_or_default(),
                ]
            })
        })
        .collect();

    let header = ["STRUCTURE", "FIELD", "TYPE", "OFFSET", "DESCRIPTION"];
    let mut widths = header.map(str::len);
    for row in &rows {
        for (w, cell) in widths.iter_mut().zip(row) {
            *w = (*w).max(cell.chars().count());
        }
    }
    let line = |cells: [&str; 5]| {
        let [w0, w1, w2, w3, _] = widths;
        println!(
            "{:<w0$}  {:<w1$}  {:<w2$}  {:<w3$}  {}",
            cells[0], cells[1], cells[2], cells[3], cells[4]
        );
    };
    line(header);
    for row in &rows {
        line(row.each_ref().map(String::as_str));
    }
}
