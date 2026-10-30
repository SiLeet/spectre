//! Query-parameter parsing and validation.
//!
//! All parsers return [`ApiError::bad_request`] with a message describing the
//! expected format. User input is never echoed back verbatim.

use spectre_core::ValueType;

use crate::error::ApiError;
use crate::{DEFAULT_READ_SIZE, DEFAULT_SEARCH_LIMIT, MAX_READ_SIZE, MAX_SEARCH_LIMIT};

/// Longest accepted free-text filter (`name`, `perms`).
const MAX_FILTER_LEN: usize = 128;

/// What `/api/read` should decode the fetched bytes as.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ReadKind {
    /// A fixed-size numeric value.
    Number(ValueType),
    /// A null-terminated string of at most `size` bytes.
    String,
    /// Raw bytes, returned as hex.
    Bytes,
}

impl ReadKind {
    /// Name as accepted by the `type` parameter.
    pub(crate) fn name(self) -> &'static str {
        match self {
            Self::Number(vt) => value_type_name(vt),
            Self::String => "string",
            Self::Bytes => "bytes",
        }
    }
}

/// A validated search value: its type and the exact bytes to look for.
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct SearchValue {
    pub(crate) value_type: ValueType,
    pub(crate) bytes: Vec<u8>,
}

fn required<'a>(value: Option<&'a str>, name: &str) -> Result<&'a str, ApiError> {
    match value.map(str::trim) {
        Some(v) if !v.is_empty() => Ok(v),
        _ => Err(ApiError::bad_request(format!(
            "missing required parameter '{name}'"
        ))),
    }
}

/// `pid`: required decimal process id.
pub(crate) fn parse_pid(value: Option<&str>) -> Result<u32, ApiError> {
    required(value, "pid")?
        .parse::<u32>()
        .map_err(|_| ApiError::bad_request("invalid 'pid': expected a decimal process id"))
}

/// `addr`: required address, `0x`-prefixed hex, decimal, or bare hex.
pub(crate) fn parse_address(value: Option<&str>) -> Result<u64, ApiError> {
    let raw = required(value, "addr")?;
    let parsed = match raw.strip_prefix("0x").or_else(|| raw.strip_prefix("0X")) {
        Some(hex) => u64::from_str_radix(hex, 16).ok(),
        None => raw
            .parse::<u64>()
            .ok()
            .or_else(|| u64::from_str_radix(raw, 16).ok()),
    };
    parsed.ok_or_else(|| ApiError::bad_request("invalid 'addr': expected hex (0x1234) or decimal"))
}

/// `type` for `/api/read`: any numeric type, `string` or `bytes`.
pub(crate) fn parse_read_kind(value: Option<&str>) -> Result<ReadKind, ApiError> {
    let raw = required(value, "type")?.to_ascii_lowercase();
    match raw.as_str() {
        "string" | "str" => Ok(ReadKind::String),
        "bytes" | "hex" => Ok(ReadKind::Bytes),
        other => numeric_type(other).map(ReadKind::Number).ok_or_else(|| {
            ApiError::bad_request(
                "invalid 'type': expected u8..u64, i8..i64, f32, f64, string or bytes",
            )
        }),
    }
}

/// `size`: optional byte count in `1..=MAX_READ_SIZE` (default 64).
pub(crate) fn parse_size(value: Option<&str>) -> Result<u32, ApiError> {
    let Some(raw) = value.map(str::trim).filter(|v| !v.is_empty()) else {
        return Ok(DEFAULT_READ_SIZE);
    };
    let size = raw
        .parse::<u32>()
        .map_err(|_| ApiError::bad_request("invalid 'size': expected a decimal byte count"))?;
    if size == 0 || size > MAX_READ_SIZE {
        return Err(ApiError::bad_request(format!(
            "invalid 'size': must be between 1 and {MAX_READ_SIZE} bytes"
        )));
    }
    Ok(size)
}

/// `endian`: optional `little` (default) or `big`. Returns `true` for little.
pub(crate) fn parse_endian(value: Option<&str>) -> Result<bool, ApiError> {
    match value.map(|v| v.trim().to_ascii_lowercase()).as_deref() {
        None | Some("") | Some("little") | Some("le") => Ok(true),
        Some("big") | Some("be") => Ok(false),
        Some(_) => Err(ApiError::bad_request(
            "invalid 'endian': expected 'little' or 'big'",
        )),
    }
}

/// `limit`: optional result cap in `1..=MAX_SEARCH_LIMIT` (default 1000).
pub(crate) fn parse_limit(value: Option<&str>) -> Result<u32, ApiError> {
    let Some(raw) = value.map(str::trim).filter(|v| !v.is_empty()) else {
        return Ok(DEFAULT_SEARCH_LIMIT);
    };
    let limit = raw
        .parse::<u32>()
        .map_err(|_| ApiError::bad_request("invalid 'limit': expected a decimal number"))?;
    if limit == 0 || limit > MAX_SEARCH_LIMIT {
        return Err(ApiError::bad_request(format!(
            "invalid 'limit': must be between 1 and {MAX_SEARCH_LIMIT}"
        )));
    }
    Ok(limit)
}

/// Optional free-text filter (`name`, `perms`); empty means "no filter".
pub(crate) fn parse_filter(value: Option<&str>, name: &str) -> Result<Option<String>, ApiError> {
    match value.map(str::trim).filter(|v| !v.is_empty()) {
        None => Ok(None),
        Some(v) if v.len() > MAX_FILTER_LEN => Err(ApiError::bad_request(format!(
            "invalid '{name}': at most {MAX_FILTER_LEN} characters"
        ))),
        Some(v) => Ok(Some(v.to_owned())),
    }
}

/// `type` + `value` for `/api/search`, encoded with the requested endianness.
pub(crate) fn parse_search_value(
    type_name: Option<&str>,
    value: Option<&str>,
    little: bool,
) -> Result<SearchValue, ApiError> {
    let type_raw = required(type_name, "type")?.to_ascii_lowercase();
    let value_type = numeric_type(&type_raw).ok_or_else(|| {
        ApiError::bad_request("invalid 'type': expected u8..u64, i8..i64, f32 or f64")
    })?;
    let raw = required(value, "value")?;
    let invalid = || {
        ApiError::bad_request(format!(
            "invalid 'value': not a valid {} (decimal, 0x-hex or float)",
            value_type_name(value_type)
        ))
    };

    let le = match value_type {
        ValueType::U8 => u8::try_from(parse_unsigned(raw).ok_or_else(invalid)?)
            .map_err(|_| invalid())?
            .to_le_bytes()
            .to_vec(),
        ValueType::U16 => u16::try_from(parse_unsigned(raw).ok_or_else(invalid)?)
            .map_err(|_| invalid())?
            .to_le_bytes()
            .to_vec(),
        ValueType::U32 => u32::try_from(parse_unsigned(raw).ok_or_else(invalid)?)
            .map_err(|_| invalid())?
            .to_le_bytes()
            .to_vec(),
        ValueType::U64 => parse_unsigned(raw)
            .ok_or_else(invalid)?
            .to_le_bytes()
            .to_vec(),
        ValueType::I8 => i8::try_from(parse_signed(raw).ok_or_else(invalid)?)
            .map_err(|_| invalid())?
            .to_le_bytes()
            .to_vec(),
        ValueType::I16 => i16::try_from(parse_signed(raw).ok_or_else(invalid)?)
            .map_err(|_| invalid())?
            .to_le_bytes()
            .to_vec(),
        ValueType::I32 => i32::try_from(parse_signed(raw).ok_or_else(invalid)?)
            .map_err(|_| invalid())?
            .to_le_bytes()
            .to_vec(),
        ValueType::I64 => parse_signed(raw)
            .ok_or_else(invalid)?
            .to_le_bytes()
            .to_vec(),
        ValueType::F32 => {
            let f = raw.parse::<f32>().map_err(|_| invalid())?;
            if !f.is_finite() {
                return Err(invalid());
            }
            f.to_le_bytes().to_vec()
        }
        ValueType::F64 => {
            let f = raw.parse::<f64>().map_err(|_| invalid())?;
            if !f.is_finite() {
                return Err(invalid());
            }
            f.to_le_bytes().to_vec()
        }
        ValueType::Bytes(_) => return Err(invalid()),
    };

    let bytes = if little {
        le
    } else {
        le.into_iter().rev().collect()
    };
    Ok(SearchValue { value_type, bytes })
}

/// Canonical name of a numeric [`ValueType`].
pub(crate) fn value_type_name(vt: ValueType) -> &'static str {
    match vt {
        ValueType::U8 => "u8",
        ValueType::U16 => "u16",
        ValueType::U32 => "u32",
        ValueType::U64 => "u64",
        ValueType::I8 => "i8",
        ValueType::I16 => "i16",
        ValueType::I32 => "i32",
        ValueType::I64 => "i64",
        ValueType::F32 => "f32",
        ValueType::F64 => "f64",
        ValueType::Bytes(_) => "bytes",
    }
}

fn numeric_type(name: &str) -> Option<ValueType> {
    Some(match name {
        "u8" => ValueType::U8,
        "u16" => ValueType::U16,
        "u32" => ValueType::U32,
        "u64" => ValueType::U64,
        "i8" => ValueType::I8,
        "i16" => ValueType::I16,
        "i32" => ValueType::I32,
        "i64" => ValueType::I64,
        "f32" => ValueType::F32,
        "f64" => ValueType::F64,
        _ => return None,
    })
}

/// Decimal or `0x`-hex unsigned integer.
fn parse_unsigned(s: &str) -> Option<u64> {
    match s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
        Some(hex) => u64::from_str_radix(hex, 16).ok(),
        None => s.parse::<u64>().ok(),
    }
}

/// Decimal (optionally negative) or `0x`-hex signed integer.
fn parse_signed(s: &str) -> Option<i64> {
    match s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
        Some(hex) => i64::from_str_radix(hex, 16).ok(),
        None => s.parse::<i64>().ok(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn address_accepts_hex_decimal_and_bare_hex() {
        assert_eq!(parse_address(Some("0x1000")).unwrap(), 0x1000);
        assert_eq!(parse_address(Some("4096")).unwrap(), 4096);
        assert_eq!(parse_address(Some("7ffe")).unwrap(), 0x7ffe);
        assert!(parse_address(Some("zz")).is_err());
        assert!(parse_address(None).is_err());
    }

    #[test]
    fn size_is_capped() {
        assert_eq!(parse_size(None).unwrap(), DEFAULT_READ_SIZE);
        assert_eq!(parse_size(Some("4096")).unwrap(), 4096);
        assert!(parse_size(Some("4097")).is_err());
        assert!(parse_size(Some("0")).is_err());
    }

    #[test]
    fn limit_has_default_and_hard_max() {
        assert_eq!(parse_limit(None).unwrap(), DEFAULT_SEARCH_LIMIT);
        assert!(parse_limit(Some("0")).is_err());
        assert!(parse_limit(Some("10001")).is_err());
    }

    #[test]
    fn search_value_checks_range_and_endianness() {
        let v = parse_search_value(Some("i16"), Some("-2"), true).unwrap();
        assert_eq!(v.bytes, (-2i16).to_le_bytes().to_vec());
        let be = parse_search_value(Some("u32"), Some("0x01020304"), false).unwrap();
        assert_eq!(be.bytes, vec![1, 2, 3, 4]);
        assert!(parse_search_value(Some("u8"), Some("256"), true).is_err());
        assert!(parse_search_value(Some("u32"), Some("abc"), true).is_err());
        assert!(parse_search_value(Some("f32"), Some("NaN"), true).is_err());
        assert!(parse_search_value(Some("string"), Some("x"), true).is_err());
    }
}
