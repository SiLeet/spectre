//! Python string semantics the bot relies on (rust-port-plan §4.3): `str.split()`,
//! `str.strip()`, `str.splitlines()`, `format(x, 'g')`, `repr()`. std's `char::is_whitespace`,
//! `str::lines` and `{}` formatting differ from Python in small, silent ways.

/// Python `str.isspace` for one char: Unicode White_Space plus `\x1c..\x1f`.
pub fn is_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// `s.split()` (no separator): whitespace runs, no empty parts.
pub fn split_ws(s: &str) -> Vec<String> {
    s.split(is_space).filter(|p| !p.is_empty()).map(str::to_owned).collect()
}

/// `s.strip()` (no argument).
pub fn strip(s: &str) -> &str {
    s.trim_matches(is_space)
}

/// `s.splitlines()`: also breaks at `\r`, `\v`, `\f`, `\x1c-\x1e`, `\x85`, U+2028/2029.
pub fn splitlines(s: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut start = 0;
    let mut it = s.char_indices().peekable();
    while let Some((i, c)) = it.next() {
        let brk = matches!(
            c,
            '\n' | '\r' | '\u{0b}' | '\u{0c}' | '\u{1c}' | '\u{1d}' | '\u{1e}' | '\u{85}' | '\u{2028}' | '\u{2029}'
        );
        if brk {
            out.push(&s[start..i]);
            let mut next = i + c.len_utf8();
            if c == '\r' && it.peek().is_some_and(|&(_, n)| n == '\n') {
                it.next();
                next += 1;
            }
            start = next;
        }
    }
    if start < s.len() {
        out.push(&s[start..]);
    }
    out
}

/// `bytes.decode(errors='replace')` (UTF-8, maximal-subpart replacement like CPython).
pub fn decode_replace(b: &[u8]) -> String {
    String::from_utf8_lossy(b).into_owned()
}

/// `format(x, 'g')`: 6 significant digits, trailing zeros dropped, exponent form
/// below 1e-4 or from 1e6 on (`1e+06`, `1.5e-05`).
pub fn fmt_g(x: f64) -> String {
    if x.is_nan() {
        return "nan".into();
    }
    if x.is_infinite() {
        return if x > 0.0 { "inf" } else { "-inf" }.into();
    }
    if x == 0.0 {
        return if x.is_sign_negative() { "-0" } else { "0" }.into();
    }
    const P: i32 = 6;
    let sci = format!("{:.*e}", (P - 1) as usize, x);
    let (mant, exp) = sci.split_once('e').expect("{:e} has an exponent");
    let exp: i32 = exp.parse().expect("integer exponent");
    if !(-4..P).contains(&exp) {
        let sign = if exp < 0 { '-' } else { '+' };
        format!("{}e{sign}{:02}", strip_zeros(mant), exp.abs())
    } else {
        strip_zeros(&format!("{:.*}", (P - 1 - exp) as usize, x)).to_owned()
    }
}

fn strip_zeros(s: &str) -> &str {
    if s.contains('.') { s.trim_end_matches('0').trim_end_matches('.') } else { s }
}

/// `format(n, 'g')` for a Python int (waits given as ints): same text as the float form
/// for |n| < 2**53, which covers every wait/millisecond value.
pub fn fmt_g_int(n: i64) -> String {
    fmt_g(n as f64)
}

/// `repr(s)` for the ASCII-ish strings the bot prints (env values, modes).
/// shortcut: non-ASCII non-printables are not escaped like CPython; only used in log lines.
pub fn repr_str(s: &str) -> String {
    let q = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::from(q);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == q => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(q);
    out
}

/// `repr(b)` for bytes: `b'device offline'`.
pub fn repr_bytes(b: &[u8]) -> String {
    let q = if b.contains(&b'\'') && !b.contains(&b'"') { b'"' } else { b'\'' };
    let mut out = String::from("b");
    out.push(q as char);
    for &c in b {
        match c {
            b'\\' => out.push_str("\\\\"),
            b'\n' => out.push_str("\\n"),
            b'\r' => out.push_str("\\r"),
            b'\t' => out.push_str("\\t"),
            c if c == q => {
                out.push('\\');
                out.push(c as char);
            }
            0x20..=0x7e => out.push(c as char),
            c => out.push_str(&format!("\\x{c:02x}")),
        }
    }
    out.push(q as char);
    out
}

/// `int(s)` for env values: optional whitespace and sign, ASCII digits, single `_` between
/// digits. shortcut: Unicode digits (`int('١')` works in Python) are not accepted.
pub fn parse_int(s: &str) -> Option<i64> {
    let t = strip(s);
    let (neg, digits) = match t.as_bytes().first() {
        Some(b'-') => (true, &t[1..]),
        Some(b'+') => (false, &t[1..]),
        _ => (false, t),
    };
    if digits.is_empty() || digits.starts_with('_') || digits.ends_with('_') || digits.contains("__") {
        return None;
    }
    let clean: String = digits.chars().filter(|&c| c != '_').collect();
    if !clean.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let v: i64 = clean.parse().ok()?;
    Some(if neg { -v } else { v })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fmt_g_matches_python() {
        // python: [format(x, 'g') for x in (...)]
        let cases = [
            (0.12, "0.12"),
            (1.5, "1.5"),
            (2.0, "2"),
            (0.5, "0.5"),
            (1e6, "1e+06"),
            (123456.0, "123456"),
            (1234567.0, "1.23457e+06"),
            (0.0001, "0.0001"),
            (0.00001, "1e-05"),
            (0.000015, "1.5e-05"),
            (999999.5, "1e+06"),
            (2.5, "2.5"),
            (0.1 + 0.2, "0.3"),
            (-3.25, "-3.25"),
            (100.0, "100"),
            (0.0, "0"),
            (-0.0, "-0"),
            (1.0 / 3.0, "0.333333"),
            (12.0, "12"),
            (0.12345678, "0.123457"),
        ];
        for (x, want) in cases {
            assert_eq!(fmt_g(x), want, "{x}");
        }
        assert_eq!(fmt_g(f64::NAN), "nan");
        assert_eq!(fmt_g(f64::INFINITY), "inf");
        assert_eq!(fmt_g_int(1000000), "1e+06");
        assert_eq!(fmt_g_int(3), "3");
    }

    #[test]
    fn round_ties_even_is_python_round() {
        // python: [round(x) for x in (0.5, 1.5, 2.5, -0.5, -1.5, 2.4999, 2.5000001)]
        let got: Vec<f64> = [0.5f64, 1.5, 2.5, -0.5, -1.5, 2.4999, 2.5000001].iter().map(|x| x.round_ties_even()).collect();
        assert_eq!(got, [0.0, 2.0, 2.0, -0.0, -2.0, 2.0, 3.0]);
    }

    #[test]
    fn split_strip_splitlines() {
        assert_eq!(split_ws("  su -c \"a b\"\x1cx\t"), ["su", "-c", "\"a", "b\"", "x"]);
        assert_eq!(strip("\x1f 12 \n"), "12");
        assert_eq!(splitlines("a\r\nb\rc\x0bd\u{85}e\n"), ["a", "b", "c", "d", "e"]);
        assert_eq!(splitlines("a\n\nb"), ["a", "", "b"]);
        assert!(splitlines("").is_empty());
    }

    #[test]
    fn reprs_and_int() {
        assert_eq!(repr_str("bogus"), "'bogus'");
        assert_eq!(repr_str("it's"), "\"it's\"");
        assert_eq!(repr_bytes(b"device offline"), "b'device offline'");
        assert_eq!(repr_bytes(b"a\x00'"), "b\"a\\x00'\"");
        assert_eq!(parse_int(" 3600 "), Some(3600));
        assert_eq!(parse_int("1_000"), Some(1000));
        assert_eq!(parse_int("-5"), Some(-5));
        assert_eq!(parse_int("1__0"), None);
        assert_eq!(parse_int("x"), None);
    }
}
