// ── Spectre Game: Offset File Validator ──────────────────────────────────
//
// Sanity checks for a game-offset YAML file: non-empty version, unique
// structure names, unique field names per structure, known field types
// (errors) and overlapping field byte ranges within a structure (warning —
// placeholder offsets may legitimately overlap until confirmed).

use std::collections::HashSet;

use serde::Serialize;
use spectre_core::FieldType;

use crate::offsets::{YamlGameFile, resolve_field_type};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Error,
    Warning,
}

/// One problem found in an offsets file.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Issue {
    pub severity: Severity,
    pub structure: Option<String>,
    pub field: Option<String>,
    pub message: String,
}

impl Issue {
    fn new(severity: Severity, structure: &str, field: Option<&str>, message: String) -> Self {
        Issue {
            severity,
            structure: Some(structure.to_owned()),
            field: field.map(str::to_owned),
            message,
        }
    }
}

/// Byte size of a field in memory.
pub fn field_size(ft: FieldType) -> u64 {
    match ft {
        FieldType::U8 | FieldType::I8 | FieldType::Bool => 1,
        FieldType::U16 | FieldType::I16 => 2,
        FieldType::U32 | FieldType::I32 | FieldType::F32 | FieldType::Pointer32 => 4,
        FieldType::U64 | FieldType::I64 | FieldType::F64 | FieldType::Pointer64 => 8,
        FieldType::String(n) => u64::from(n),
    }
}

/// Validate an offsets file.  An empty result means "ok".
pub fn validate(file: &YamlGameFile) -> Vec<Issue> {
    let mut issues = Vec::new();

    if file.version.trim().is_empty() {
        issues.push(Issue {
            severity: Severity::Error,
            structure: None,
            field: None,
            message: "game version is missing or empty".to_owned(),
        });
    }

    let mut struct_names = HashSet::new();
    for sd in &file.structures {
        if !struct_names.insert(sd.name.as_str()) {
            issues.push(Issue::new(
                Severity::Error,
                &sd.name,
                None,
                "duplicate structure name".to_owned(),
            ));
        }

        let mut field_names = HashSet::new();
        // (start, end, name) of every field with a known type.
        let mut ranges = Vec::new();
        for f in &sd.fields {
            if !field_names.insert(f.name.as_str()) {
                issues.push(Issue::new(
                    Severity::Error,
                    &sd.name,
                    Some(&f.name),
                    "duplicate field name".to_owned(),
                ));
            }
            match resolve_field_type(f) {
                Some(ft) => {
                    ranges.push((f.offset, f.offset.saturating_add(field_size(ft)), &f.name))
                }
                None => issues.push(Issue::new(
                    Severity::Error,
                    &sd.name,
                    Some(&f.name),
                    format!("unknown field type '{}'", f.field_type),
                )),
            }
        }

        ranges.sort();
        // The field reaching furthest so far; any later start below its end overlaps it.
        let mut furthest: Option<(u64, u64, &String)> = None;
        for (start, end, name) in ranges {
            if let Some((pstart, pend, pname)) = furthest {
                if start < pend {
                    issues.push(Issue::new(
                        Severity::Warning,
                        &sd.name,
                        Some(name),
                        format!(
                            "bytes {start:#x}..{end:#x} overlap field '{pname}' ({pstart:#x}..{pend:#x})"
                        ),
                    ));
                }
                if end <= pend {
                    continue;
                }
            }
            furthest = Some((start, end, name));
        }
    }

    issues
}
