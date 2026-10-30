use crate::LuaContext;
/// Lua API — registers Spectre and Bot modules on a Lua instance.
///
/// Each Rust callback retrieves the shared `LuaContext` from app-data,
/// then delegates to the `MemoryReader` or `BotApi` implementations.
use mlua::{Error as LuaError, IntoLua, Lua, Result as LuaResult, Table, Value};
use spectre_core::{MemoryReader, PatternField, ScanPattern, ScanValue, ValueType};

/// Stateless helper: registers all functions on an initialised Lua instance.
pub struct LuaApi;

impl LuaApi {
    /// Register the `spectre` and `bot` modules into `_G`.
    ///
    /// Must be called after `Lua::set_app_data()` has been called with a
    /// `LuaContext` so that callbacks can retrieve their backends.
    pub fn register(lua: &Lua) -> anyhow::Result<()> {
        register_spectre(lua)?;
        register_bot(lua)?;
        Ok(())
    }
}

// ── Helpers ────────────────────────────────────────────────────────

/// Retrieve the shared context from the Lua instance's app-data.
fn get_ctx(lua: &Lua) -> mlua::AppDataRef<'_, LuaContext> {
    lua.app_data_ref::<LuaContext>()
        .expect("LuaContext app data must be set before modules are registered")
}

/// Build a `ScanPattern` from a Lua table.
///
/// Expected Lua table shape:
/// ```lua
/// {
///   name   = "player_hp",
///   pid    = 1234,            -- optional; falls back to first known process
///   fields = {
///     { name = "hp",  type = "u32",  value = { int = { 100, 500 } }, alignment = 4 },
///     { name = "id",  type = "u32",  value = { exact = { 0x12, 0x34 } } },
///     { name = "x",   type = "f32",  value = 100.5 },   -- plain number = exact singleton range
///   },
/// }
/// ```
fn pattern_table_to_scan_pattern(tbl: &Table) -> LuaResult<ScanPattern> {
    let name: String = tbl
        .get::<Option<String>>("name")?
        .unwrap_or_else(|| "pattern".to_string());

    let mut fields: Vec<PatternField> = Vec::new();
    let mut idx: usize = 1;
    loop {
        let field_tbl: Option<Table> = tbl.get(idx)?;
        match field_tbl {
            Some(ft) => fields.push(field_table_to_pattern_field(&ft)?),
            None => break,
        }
        idx += 1;
    }

    if fields.is_empty() {
        return Err(LuaError::RuntimeError(
            "scan pattern table must have a non-empty `fields` array".to_string(),
        ));
    }

    Ok(ScanPattern { name, fields })
}

/// Convert one Lua field table `{ name, type, value, alignment }` into a
/// [`PatternField`].
fn field_table_to_pattern_field(tbl: &Table) -> LuaResult<PatternField> {
    let name: String = tbl
        .get::<Option<String>>("name")?
        .unwrap_or_else(|| "field".to_string());

    let value_type: ValueType = match tbl.get::<Option<String>>("type")? {
        Some(t) => type_str_to_value_type(&t)?,
        None => ValueType::U32,
    };

    let alignment: u32 = tbl.get::<Option<u32>>("alignment")?.unwrap_or(4);

    let value_raw: Value = tbl.get("value")?;
    let value: ScanValue = lua_value_to_scan_value(&value_raw, value_type)?;

    Ok(PatternField {
        name,
        value_type,
        value,
        alignment,
    })
}

/// Convert a Lua type string to a `ValueType`.
fn type_str_to_value_type(s: &str) -> LuaResult<ValueType> {
    match s.to_lowercase().as_str() {
        "u8" => Ok(ValueType::U8),
        "u16" => Ok(ValueType::U16),
        "u32" => Ok(ValueType::U32),
        "u64" => Ok(ValueType::U64),
        "i8" => Ok(ValueType::I8),
        "i16" => Ok(ValueType::I16),
        "i32" => Ok(ValueType::I32),
        "i64" => Ok(ValueType::I64),
        "f32" => Ok(ValueType::F32),
        "f64" => Ok(ValueType::F64),
        other => Err(LuaError::RuntimeError(format!("unknown type: {}", other))),
    }
}

/// Convert a Lua value to a `ScanValue`.
///
/// Supported shapes:
/// - `{ exact = { 0x12, 0x34, ... } }` → [`ScanValue::Exact`]
/// - `{ int = { lo, hi } }` or `{ int = { lo = a, hi = b } }` → [`ScanValue::IntRange`]
/// - `{ float = { lo, hi } }` or `{ float = { lo = a, hi = b } }` → [`ScanValue::FloatRange`]
/// - a plain number → exact singleton range (int or float depending on `vt`)
/// - anything else → [`ScanValue::Any`]
fn lua_value_to_scan_value(v: &Value, vt: ValueType) -> LuaResult<ScanValue> {
    match v {
        Value::Integer(i) => Ok(match vt {
            ValueType::F32 | ValueType::F64 | ValueType::Bytes(_) => {
                ScanValue::FloatRange(*i as f64, *i as f64)
            }
            _ => ScanValue::IntRange(*i, *i),
        }),
        Value::Number(n) => Ok(ScanValue::FloatRange(*n, *n)),
        Value::Table(tbl) => {
            // "exact" — a list of byte values
            if let Some(exact_tbl) = tbl.get::<Option<Table>>("exact")? {
                let mut data: Vec<u8> = Vec::new();
                for b in exact_tbl.sequence_values::<u32>() {
                    data.push((b? & 0xFF) as u8);
                }
                return Ok(ScanValue::Exact(data));
            }

            // "int" range { lo, hi } (array form or named keys)
            if let Some(int_tbl) = tbl.get::<Option<Table>>("int")? {
                let lo: i64 = int_tbl
                    .get::<Option<i64>>(1)?
                    .or(int_tbl.get::<Option<i64>>("lo")?)
                    .unwrap_or(0);
                let hi: i64 = int_tbl
                    .get::<Option<i64>>(2)?
                    .or(int_tbl.get::<Option<i64>>("hi")?)
                    .unwrap_or(i64::MAX);
                return Ok(ScanValue::IntRange(lo, hi));
            }

            // "float" range { lo, hi }
            if let Some(flt_tbl) = tbl.get::<Option<Table>>("float")? {
                let lo: f64 = flt_tbl
                    .get::<Option<f64>>(1)?
                    .or(flt_tbl.get::<Option<f64>>("lo")?)
                    .unwrap_or(f64::NEG_INFINITY);
                let hi: f64 = flt_tbl
                    .get::<Option<f64>>(2)?
                    .or(flt_tbl.get::<Option<f64>>("hi")?)
                    .unwrap_or(f64::INFINITY);
                return Ok(ScanValue::FloatRange(lo, hi));
            }

            // Fallback: any
            Ok(ScanValue::Any)
        }
        _ => Ok(ScanValue::Any),
    }
}

/// Value kinds supported by `spectre.read_fields`.
#[derive(Debug, Clone, Copy)]
enum FieldKind {
    U8,
    U16,
    U32,
    U64,
    I32,
    I64,
    F32,
    F64,
    /// Null-terminated string of at most `len` bytes.
    Str(u32),
}

/// One validated entry of a `read_fields` request.
#[derive(Debug)]
struct FieldSpec {
    name: String,
    addr: u64,
    kind: FieldKind,
}

/// Validate one `{ name, addr, type, len }` entry (1-based `idx` for errors).
///
/// `type` defaults to `"u32"` (same default as `spectre.scan` fields);
/// `len` is required for `"string"`.
fn field_spec_from_table(idx: usize, tbl: &Table) -> LuaResult<FieldSpec> {
    let name: String = tbl.get::<Option<String>>("name")?.ok_or_else(|| {
        LuaError::RuntimeError(format!("read_fields: entry {idx} is missing `name`"))
    })?;
    let addr: u64 = tbl.get::<Option<u64>>("addr")?.ok_or_else(|| {
        LuaError::RuntimeError(format!("read_fields: `{name}` is missing `addr`"))
    })?;
    let type_str: String = tbl
        .get::<Option<String>>("type")?
        .unwrap_or_else(|| "u32".to_string());

    let kind = match type_str.to_lowercase().as_str() {
        "u8" => FieldKind::U8,
        "u16" => FieldKind::U16,
        "u32" => FieldKind::U32,
        "u64" => FieldKind::U64,
        "i32" => FieldKind::I32,
        "i64" => FieldKind::I64,
        "f32" => FieldKind::F32,
        "f64" => FieldKind::F64,
        "string" => {
            let len: u32 = tbl.get::<Option<u32>>("len")?.ok_or_else(|| {
                LuaError::RuntimeError(format!(
                    "read_fields: `{name}` has type \"string\" but no `len`"
                ))
            })?;
            FieldKind::Str(len)
        }
        other => {
            return Err(LuaError::RuntimeError(format!(
                "read_fields: `{name}` has unknown type: {other}"
            )));
        }
    };

    Ok(FieldSpec { name, addr, kind })
}

/// Perform the read for one validated field and convert it to a Lua value
/// (same conversions as the single `read_*` functions).
fn read_field(
    lua: &Lua,
    reader: &dyn MemoryReader,
    pid: u32,
    spec: &FieldSpec,
) -> anyhow::Result<Value> {
    let addr = spec.addr;
    let value = match spec.kind {
        FieldKind::U8 => reader.read_u8(pid, addr)?.into_lua(lua)?,
        FieldKind::U16 => reader.read_u16(pid, addr, true)?.into_lua(lua)?,
        FieldKind::U32 => reader.read_u32(pid, addr, true)?.into_lua(lua)?,
        FieldKind::U64 => reader.read_u64(pid, addr, true)?.into_lua(lua)?,
        FieldKind::I32 => reader.read_i32(pid, addr, true)?.into_lua(lua)?,
        FieldKind::I64 => reader.read_i64(pid, addr, true)?.into_lua(lua)?,
        FieldKind::F32 => reader.read_f32(pid, addr, true)?.into_lua(lua)?,
        FieldKind::F64 => reader.read_f64(pid, addr, true)?.into_lua(lua)?,
        FieldKind::Str(len) => reader.read_string(pid, addr, len)?.into_lua(lua)?,
    };
    Ok(value)
}

// ── Spectre Module ─────────────────────────────────────────────────

fn register_spectre(lua: &Lua) -> anyhow::Result<()> {
    let m = lua.create_table()?;

    // spectre.read_u32(pid, address) -> number
    m.set(
        "read_u32",
        lua.create_function(|lua: &Lua, (pid, addr): (u32, u64)| -> LuaResult<u32> {
            let ctx = get_ctx(lua);
            Ok(ctx.reader.read_u32(pid, addr, true)?)
        })?,
    )?;

    // spectre.read_u64(pid, address) -> number
    m.set(
        "read_u64",
        lua.create_function(|lua: &Lua, (pid, addr): (u32, u64)| -> LuaResult<u64> {
            let ctx = get_ctx(lua);
            Ok(ctx.reader.read_u64(pid, addr, true)?)
        })?,
    )?;

    // spectre.read_i32(pid, address) -> number
    m.set(
        "read_i32",
        lua.create_function(|lua: &Lua, (pid, addr): (u32, u64)| -> LuaResult<i32> {
            let ctx = get_ctx(lua);
            Ok(ctx.reader.read_i32(pid, addr, true)?)
        })?,
    )?;

    // spectre.read_f32(pid, address) -> number
    m.set(
        "read_f32",
        lua.create_function(|lua: &Lua, (pid, addr): (u32, u64)| -> LuaResult<f32> {
            let ctx = get_ctx(lua);
            Ok(ctx.reader.read_f32(pid, addr, true)?)
        })?,
    )?;

    // spectre.read_string(pid, address, length) -> string
    m.set(
        "read_string",
        lua.create_function(
            |lua: &Lua, (pid, addr, len): (u32, u64, u32)| -> LuaResult<String> {
                let ctx = get_ctx(lua);
                Ok(ctx.reader.read_string(pid, addr, len)?)
            },
        )?,
    )?;

    // spectre.read_fields(pid, fields_table) -> { name -> number|string }
    //
    // Batch read: every entry is validated up front (bad shape / unknown
    // type / missing `len` for strings raises a Lua error before any read).
    // A read that fails for one entry leaves that name absent from the
    // result (i.e. `result.name == nil`); the remaining entries still succeed.
    m.set(
        "read_fields",
        lua.create_function(
            |lua: &Lua, (pid, fields): (u32, Table)| -> LuaResult<Table> {
                let specs: Vec<FieldSpec> = fields
                    .sequence_values::<Table>()
                    .enumerate()
                    .map(|(i, entry)| field_spec_from_table(i + 1, &entry?))
                    .collect::<LuaResult<_>>()?;

                let ctx = get_ctx(lua);
                let result = lua.create_table()?;
                for spec in &specs {
                    match read_field(lua, &*ctx.reader, pid, spec) {
                        Ok(value) => result.set(spec.name.as_str(), value)?,
                        Err(e) => tracing::debug!(
                            "read_fields: `{}` at {:#x} failed: {e:#}",
                            spec.name,
                            spec.addr
                        ),
                    }
                }
                Ok(result)
            },
        )?,
    )?;

    // spectre.regions(pid) -> { { start, end_addr, ["end"], size, perms, path }, ... }
    m.set(
        "regions",
        lua.create_function(|lua: &Lua, pid: u32| -> LuaResult<Table> {
            let ctx = get_ctx(lua);
            let regions = ctx.reader.memory_regions(pid)?;

            let list = lua.create_table()?;
            for (i, region) in regions.iter().enumerate() {
                let r = lua.create_table()?;
                r.set("start", region.start)?;
                // `end` is a Lua keyword, so `r.end` does not parse; expose the
                // ergonomic `end_addr` plus `end` for `r["end"]` access.
                r.set("end_addr", region.end)?;
                r.set("end", region.end)?;
                r.set("size", region.size())?;
                r.set("perms", region.perms.as_str())?;
                if let Some(path) = &region.path {
                    r.set("path", path.as_str())?;
                }
                list.set(i + 1, r)?;
            }
            Ok(list)
        })?,
    )?;

    // spectre.find_process(name) -> pid or nil
    m.set(
        "find_process",
        lua.create_function(|lua: &Lua, name: String| -> LuaResult<Option<u32>> {
            let ctx = get_ctx(lua);
            let processes = ctx.reader.find_process(&name)?;
            Ok(processes.first().map(|p| p.pid))
        })?,
    )?;

    // spectre.scan(pattern_table) -> table of addresses
    //
    // Accepts a single pattern table `{ name=…, fields={…} }` (returning a
    // list of matched addresses) or an array of pattern tables (returning a
    // map of pattern name -> list of matched addresses). A `pid` key inside
    // the pattern table overrides the default first-known-process target.
    m.set(
        "scan",
        lua.create_function(|lua: &Lua, pattern_tbl: Table| -> LuaResult<Value> {
            let ctx = get_ctx(lua);

            // Optional explicit pid; fall back to the first known process.
            let explicit_pid: Option<u32> = pattern_tbl.get("pid")?;
            let pid: u32 = match explicit_pid {
                Some(p) => p,
                None => {
                    let processes = ctx.reader.list_processes()?;
                    match processes.first() {
                        Some(p) => p.pid,
                        None => return Ok(Value::Table(lua.create_table()?)),
                    }
                }
            };

            // Distinguish a single pattern table from an array of them.
            let first: Option<Table> = pattern_tbl.get(1)?;
            let is_array = first.is_some();

            let mut patterns: Vec<ScanPattern> = Vec::new();
            if is_array {
                let mut idx: usize = 1;
                loop {
                    let entry: Option<Table> = pattern_tbl.get(idx)?;
                    match entry {
                        Some(t) => patterns.push(pattern_table_to_scan_pattern(&t)?),
                        None => break,
                    }
                    idx += 1;
                }
            } else {
                patterns.push(pattern_table_to_scan_pattern(&pattern_tbl)?);
            }

            if patterns.is_empty() {
                return Ok(Value::Table(lua.create_table()?));
            }

            let config = spectre_core::ScanConfig::default();
            let reports = spectre_core::scan_memory(&*ctx.reader, pid, patterns, &config)?;

            let result_tbl = lua.create_table()?;
            for report in &reports {
                let addr_list = lua.create_table()?;
                for (i, mt) in report.matches.iter().enumerate() {
                    addr_list.set(i + 1, mt.address)?;
                }
                result_tbl.set(report.pattern_name.clone(), addr_list)?;
            }

            Ok(Value::Table(result_tbl))
        })?,
    )?;

    lua.globals().set("spectre", m)?;
    Ok(())
}

// ── Bot Module ─────────────────────────────────────────────────────

fn register_bot(lua: &Lua) -> anyhow::Result<()> {
    let m = lua.create_table()?;

    // bot.click(x, y) -> bool
    m.set(
        "click",
        lua.create_function(|lua: &Lua, (x, y): (u32, u32)| -> LuaResult<bool> {
            let ctx = get_ctx(lua);
            Ok(ctx.bot.click(x, y)?)
        })?,
    )?;

    // bot.swipe(x1, y1, x2, y2, duration) -> bool
    m.set(
        "swipe",
        lua.create_function(
            |lua: &Lua, (x1, y1, x2, y2, dur): (u32, u32, u32, u32, u32)| -> LuaResult<bool> {
                let ctx = get_ctx(lua);
                Ok(ctx.bot.swipe(x1, y1, x2, y2, dur)?)
            },
        )?,
    )?;

    // bot.wait(ms) -> nil
    m.set(
        "wait",
        lua.create_function(|lua: &Lua, ms: u32| -> LuaResult<()> {
            let ctx = get_ctx(lua);
            ctx.bot.wait(ms)?;
            Ok(())
        })?,
    )?;

    // bot.log(message) -> nil
    m.set(
        "log",
        lua.create_function(|lua: &Lua, message: String| -> LuaResult<()> {
            let ctx = get_ctx(lua);
            ctx.bot.log(&message)?;
            Ok(())
        })?,
    )?;

    lua.globals().set("bot", m)?;
    Ok(())
}
