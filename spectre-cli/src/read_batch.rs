//! `spectre read-batch --offsets <game|yaml> --pid P --base 0x.. [--adb] [--json]`
//! — read EVERY field of an offsets YAML in one process run through one
//! reader (one attach / region cache instead of one CLI start per value).
//! Validation is the same as `spectre offsets` (`spectre_game::validate`);
//! a field with a validation error or a failed read is reported in its own
//! entry (`valid: false`, `note`) and never stops the rest.

use anyhow::{Result, anyhow};
use serde::Serialize;
use serde_json::{Value, json};
use structopt::StructOpt;

use spectre_core::FieldType;
use spectre_game::offsets::{read_yaml_file, resolve_field_type};
use spectre_game::validate::field_size;
use spectre_game::{Severity, YamlGameFile, validate};

#[derive(StructOpt)]
pub struct ReadBatchArgs {
    /// Game name or path to an offsets YAML (same lookup as `spectre offsets`).
    #[structopt(long = "offsets")]
    pub offsets: String,

    /// Target process ID.
    #[structopt(long = "pid")]
    pub pid: u32,

    /// Base address the structure offsets are relative to (hex, e.g. 0x724DF0000000).
    #[structopt(long = "base")]
    pub base: String,

    /// Read through ADB (Android device / emulator).
    #[structopt(long = "adb")]
    pub adb: bool,

    /// Output as JSON (array of entries); otherwise one `name = value` line each.
    #[structopt(long = "json")]
    pub json: bool,
}

/// One field to read, after validation.
#[derive(Debug, Clone, PartialEq)]
pub struct Planned {
    pub name: String,
    pub address: u64,
    pub fmt: String,
    pub field_type: Option<FieldType>,
    pub valid: bool,
    pub note: Option<String>,
}

/// One result row of the JSON output.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Entry {
    pub name: String,
    pub address: String,
    pub value: Value,
    pub fmt: String,
    pub valid: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// Every field of `file` with its absolute address and validation verdict.
pub fn plan(file: &YamlGameFile, base: u64) -> Vec<Planned> {
    let issues = validate(file);
    let mut out = Vec::new();
    for sd in &file.structures {
        for f in &sd.fields {
            let hits: Vec<_> = issues
                .iter()
                .filter(|i| i.structure.as_deref() == Some(sd.name.as_str()))
                .filter(|i| i.field.as_deref().is_none_or(|n| n == f.name))
                .collect();
            let field_type = resolve_field_type(f);
            let error = hits.iter().any(|i| i.severity == Severity::Error) || field_type.is_none();
            let mut notes: Vec<String> = hits.iter().map(|i| i.message.clone()).collect();
            if field_type.is_none() && !notes.iter().any(|n| n.starts_with("unknown field type")) {
                notes.push(format!("unknown field type '{}'", f.field_type));
            }
            out.push(Planned {
                name: format!("{}.{}", sd.name, f.name),
                address: base.wrapping_add(sd.base_offset).wrapping_add(f.offset),
                fmt: f.field_type.clone(),
                field_type,
                valid: !error,
                note: (!notes.is_empty()).then(|| notes.join("; ")),
            });
        }
    }
    out
}

/// Bytes -> JSON value for one field type (little endian, like the reader).
pub fn decode(ft: FieldType, b: &[u8]) -> Option<Value> {
    let a = |n: usize| -> Option<&[u8]> { b.get(..n) };
    Some(match ft {
        FieldType::U8 => json!(b.first()?),
        FieldType::I8 => json!(*b.first()? as i8),
        FieldType::Bool => json!(*b.first()? != 0),
        FieldType::U16 => json!(u16::from_le_bytes(a(2)?.try_into().ok()?)),
        FieldType::I16 => json!(i16::from_le_bytes(a(2)?.try_into().ok()?)),
        FieldType::U32 => json!(u32::from_le_bytes(a(4)?.try_into().ok()?)),
        FieldType::I32 => json!(i32::from_le_bytes(a(4)?.try_into().ok()?)),
        FieldType::F32 => json!(f32::from_le_bytes(a(4)?.try_into().ok()?)),
        FieldType::U64 => json!(u64::from_le_bytes(a(8)?.try_into().ok()?)),
        FieldType::I64 => json!(i64::from_le_bytes(a(8)?.try_into().ok()?)),
        FieldType::F64 => json!(f64::from_le_bytes(a(8)?.try_into().ok()?)),
        FieldType::Pointer32 => json!(format!("{:#x}", u32::from_le_bytes(a(4)?.try_into().ok()?))),
        FieldType::Pointer64 => json!(format!("{:#x}", u64::from_le_bytes(a(8)?.try_into().ok()?))),
        FieldType::String(_) => {
            let end = b.iter().position(|&c| c == 0).unwrap_or(b.len());
            json!(String::from_utf8_lossy(&b[..end]))
        }
    })
}

fn size_of(ft: FieldType) -> u32 {
    match ft {
        FieldType::String(n) => n,
        other => field_size(other) as u32,
    }
}

/// Read every valid planned field through `read(address, size)`; failures
/// stay in their own entry.
pub fn read_all(read: &dyn Fn(u64, u32) -> Result<Vec<u8>>, planned: &[Planned]) -> Vec<Entry> {
    planned
        .iter()
        .map(|p| {
            let mut e = Entry {
                name: p.name.clone(),
                address: format!("{:#x}", p.address),
                value: Value::Null,
                fmt: p.fmt.clone(),
                valid: false,
                note: p.note.clone(),
            };
            let Some(ft) = p.field_type.filter(|_| p.valid) else {
                return e;
            };
            match read(p.address, size_of(ft)).map(|b| decode(ft, &b)) {
                Ok(Some(v)) => {
                    e.value = v;
                    e.valid = true;
                }
                Ok(None) => e.note = Some("short read".to_owned()),
                Err(err) => e.note = Some(format!("read failed: {err}")),
            }
            e
        })
        .collect()
}

pub fn run_read_batch(args: ReadBatchArgs) -> Result<()> {
    let path = crate::offsets::resolve_offsets_path(&args.offsets)?;
    let file = read_yaml_file(&path)?;
    let base = u64::from_str_radix(args.base.trim_start_matches("0x").trim_start_matches("0X"), 16)
        .map_err(|e| anyhow!("--base '{}' is not hex: {e}", args.base))?;
    let planned = plan(&file, base);
    let reader = crate::create_reader(args.adb, None, None)?; // one reader for every field
    let entries = read_all(&|addr, size| reader.read_bytes(args.pid, addr, size), &planned);
    if args.json {
        println!("{}", serde_json::to_string_pretty(&entries)?);
    } else {
        for e in &entries {
            let note = e.note.as_deref().map(|n| format!("  ({n})")).unwrap_or_default();
            println!("{} @ {} = {}{note}", e.name, e.address, e.value);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const YAML: &str = r#"
game: "test-game"
version: "1.0"
structures:
  - name: "Player"
    base_offset: 0x100
    fields:
      - { name: "power", field_type: U32, offset: 0x10 }
      - { name: "gold", field_type: U64, offset: 0x18 }
      - { name: "nick", field_type: String(8), offset: 0x20 }
      - { name: "weird", field_type: Banana, offset: 0x30 }
"#;

    fn file() -> YamlGameFile {
        serde_yaml::from_str(YAML).unwrap()
    }

    #[test]
    fn plan_resolves_addresses_and_types() {
        let p = plan(&file(), 0x7000_0000);
        assert_eq!(p.len(), 4);
        assert_eq!(p[0].name, "Player.power");
        assert_eq!(p[0].address, 0x7000_0110);
        assert_eq!(p[0].field_type, Some(FieldType::U32));
        assert!(p[0].valid);
        assert_eq!(p[2].field_type, Some(FieldType::String(8)));
        assert!(!p[3].valid);
        assert!(p[3].note.as_deref().unwrap().contains("unknown field type"));
        assert_eq!(p[3].note.as_deref().unwrap().matches("unknown field type").count(), 1);
    }

    #[test]
    fn decode_types() {
        assert_eq!(decode(FieldType::U32, &259_850u32.to_le_bytes()), Some(json!(259_850)));
        assert_eq!(decode(FieldType::I16, &(-2i16).to_le_bytes()), Some(json!(-2)));
        assert_eq!(decode(FieldType::F32, &1.5f32.to_le_bytes()), Some(json!(1.5)));
        assert_eq!(decode(FieldType::Bool, &[1]), Some(json!(true)));
        assert_eq!(decode(FieldType::String(8), b"SiLeet\0\0"), Some(json!("SiLeet")));
        assert_eq!(decode(FieldType::Pointer64, &0x7000u64.to_le_bytes()), Some(json!("0x7000")));
        assert_eq!(decode(FieldType::U64, &[1, 2]), None); // short read
    }

    #[test]
    fn one_broken_entry_does_not_kill_the_rest() {
        let planned = plan(&file(), 0);
        let read = |addr: u64, size: u32| -> Result<Vec<u8>> {
            match addr {
                0x118 => Err(anyhow!("EFAULT")),
                0x110 => Ok(259_850u32.to_le_bytes().to_vec()),
                _ => Ok(vec![b'A'; size as usize]),
            }
        };
        let e = read_all(&read, &planned);
        assert_eq!((e[0].value.clone(), e[0].valid), (json!(259_850), true));
        assert_eq!((e[1].value.clone(), e[1].valid), (Value::Null, false));
        assert_eq!(e[1].note.as_deref(), Some("read failed: EFAULT"));
        assert_eq!(e[2].value, json!("AAAAAAAA"));
        assert!(!e[3].valid); // invalid type: never read
    }

    #[test]
    fn json_shape() {
        let e = read_all(&|_, _| Ok(5u32.to_le_bytes().to_vec()), &plan(&file(), 0)[..1]);
        let v = serde_json::to_value(&e).unwrap();
        assert_eq!(
            v,
            json!([{ "name": "Player.power", "address": "0x110", "value": 5, "fmt": "U32", "valid": true }])
        );
    }

    #[test]
    fn validation_errors_mark_entries_invalid() {
        let bad: YamlGameFile = serde_yaml::from_str(
            r#"
game: "g"
version: "1"
structures:
  - name: "S"
    base_offset: 0x0
    fields:
      - { name: "a", field_type: U32, offset: 0x0 }
      - { name: "a", field_type: U32, offset: 0x4 }
"#,
        )
        .unwrap();
        let errors = validate(&bad).iter().any(|i| i.severity == Severity::Error);
        assert!(errors, "duplicate field name should be a validation error");
        assert!(plan(&bad, 0).iter().any(|e| !e.valid));
    }
}
