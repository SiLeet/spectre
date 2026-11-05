//! `.spectre/afk-bot.lock`, byte-compatible with `scripts/_bot_lock.py` (pulled forward from
//! E4: every live Rust call must respect it). Same path, PID as ASCII text, mtime staleness
//! (`AFK_LOCK_STALE`, default 3600 s), `AFK_BOT_LOCK_HELD=1` inherits the wrapper's lock,
//! release only when the file carries OUR pid. The take-over keeps Python's TOCTOU window
//! (stat, then truncate+write - no `create_new`, PY-NOTE-06): two takers can both win.

use crate::pystr::{parse_int, strip};
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

pub const HELD_ENV: &str = "AFK_BOT_LOCK_HELD";
pub const STALE_ENV: &str = "AFK_LOCK_STALE";

/// `REPO / '.spectre' / 'afk-bot.lock'`.
pub fn default_lock(repo: &Path) -> PathBuf {
    repo.join(".spectre").join("afk-bot.lock")
}

#[derive(Debug)]
pub enum LockError {
    /// `int(env['AFK_LOCK_STALE'])` raised (Python: ValueError).
    BadStale(String),
    Io(std::io::Error),
}

impl std::fmt::Display for LockError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LockError::BadStale(v) => write!(f, "invalid literal for int() with base 10: {v:?}"),
            LockError::Io(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for LockError {}

impl From<std::io::Error> for LockError {
    fn from(e: std::io::Error) -> Self {
        LockError::Io(e)
    }
}

/// `path.stat().st_mtime` as float seconds; None if the file is missing.
fn mtime(path: &Path) -> std::io::Result<Option<f64>> {
    match std::fs::metadata(path) {
        Ok(m) => Ok(Some(m.modified()?.duration_since(UNIX_EPOCH).map_or(0.0, |d| d.as_secs_f64()))),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e),
    }
}

/// `read_text(encoding='ascii', errors='replace')`: every non-ASCII byte becomes U+FFFD.
fn read_ascii(path: &Path) -> std::io::Result<String> {
    Ok(std::fs::read(path)?.into_iter().map(|b| if b < 0x80 { b as char } else { '\u{fffd}' }).collect())
}

fn now_s() -> f64 {
    std::time::SystemTime::now().duration_since(UNIX_EPOCH).map_or(0.0, |d| d.as_secs_f64())
}

/// `acquire(lock, env, stale, now)`: True when the caller may tap (acquired or inherited),
/// False when another live run holds a lock younger than `stale` seconds.
pub fn acquire(
    lock: &Path,
    env: &dyn Fn(&str) -> Option<String>,
    stale: Option<i64>,
    now: Option<f64>,
    pid: u32,
) -> Result<bool, LockError> {
    let stale = match stale {
        Some(s) => s,
        None => {
            let raw = env(STALE_ENV).unwrap_or_else(|| "3600".into());
            parse_int(&raw).ok_or(LockError::BadStale(raw))?
        }
    };
    let now = now.unwrap_or_else(now_s);
    if env(HELD_ENV).as_deref() == Some("1") {
        return Ok(true);
    }
    if let Some(m) = mtime(lock)?
        && now - m < stale as f64
    {
        return Ok(false);
    }
    if let Some(parent) = lock.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(lock, pid.to_string())?;
    Ok(true)
}

/// `release(lock, env)`: drop the lock only if WE created it (never a wrapper's lock).
pub fn release(lock: &Path, env: &dyn Fn(&str) -> Option<String>, pid: u32) -> Result<(), LockError> {
    if env(HELD_ENV).as_deref() == Some("1") {
        return Ok(());
    }
    let text = match read_ascii(lock) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(e) => return Err(e.into()),
    };
    if strip(&text) == pid.to_string() {
        match std::fs::remove_file(lock) {
            Err(e) if e.kind() != std::io::ErrorKind::NotFound => return Err(e.into()),
            _ => {}
        }
    }
    Ok(())
}

/// `describe(lock)`: `pid <owner>, age <s>s` or `no lock file`.
pub fn describe(lock: &Path, now: Option<f64>) -> Result<String, LockError> {
    let owner = match read_ascii(lock) {
        Ok(t) => strip(&t).to_owned(),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok("no lock file".into()),
        Err(e) => return Err(e.into()),
    };
    let Some(m) = mtime(lock)? else { return Ok("no lock file".into()) };
    let age = ((now.unwrap_or_else(now_s) - m) as i64).max(0);
    Ok(format!("pid {}, age {age}s", if owner.is_empty() { "?" } else { &owner }))
}

/// `os.environ` as the env getter.
pub fn os_env(key: &str) -> Option<String> {
    std::env::var(key).ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn tmp(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("spectre-afk-lock-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        d.join("sub").join("afk-bot.lock")
    }

    fn env(map: &[(&str, &str)]) -> impl Fn(&str) -> Option<String> {
        let m: HashMap<String, String> = map.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect();
        move |k| m.get(k).cloned()
    }

    #[test]
    fn semantics_like_bot_lock_py() {
        let lock = tmp("sem");
        let e = env(&[]);
        assert!(acquire(&lock, &e, None, None, 4242).unwrap()); // free -> own pid written
        assert_eq!(std::fs::read_to_string(&lock).unwrap(), "4242");
        assert!(!acquire(&lock, &e, None, None, 1).unwrap()); // fresh foreign -> refused
        let later = now_s() + 3601.0;
        assert!(acquire(&lock, &e, None, Some(later), 7).unwrap()); // stale -> taken over
        assert_eq!(std::fs::read_to_string(&lock).unwrap(), "7");
        assert!(!acquire(&lock, &env(&[(STALE_ENV, "99999")]), None, Some(later), 8).unwrap());
        assert!(acquire(&lock, &env(&[(HELD_ENV, "1")]), None, None, 9).unwrap()); // inherited
        assert_eq!(std::fs::read_to_string(&lock).unwrap(), "7"); // ... and untouched
        assert!(matches!(acquire(&lock, &env(&[(STALE_ENV, "x")]), None, None, 1), Err(LockError::BadStale(_))));
        release(&lock, &e, 4242).unwrap(); // not ours -> kept
        assert!(lock.exists());
        assert!(describe(&lock, None).unwrap().starts_with("pid 7, age "));
        release(&lock, &e, 7).unwrap();
        assert!(!lock.exists());
        assert_eq!(describe(&lock, None).unwrap(), "no lock file");
        release(&lock, &e, 7).unwrap(); // missing -> fine
        let _ = std::fs::remove_dir_all(lock.parent().unwrap().parent().unwrap());
    }
}
