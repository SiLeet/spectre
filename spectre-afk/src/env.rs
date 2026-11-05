//! Process environment (afk_claim_vision `REPO`, `ADB`, `SERIAL`, `TMP`, `AFK_TAP_MODE`).

use crate::infra::tap::TapMode;
use crate::pystr::repr_str;
use std::path::PathBuf;

/// `SERIAL`: every adb call is `adb -s 127.0.0.1:5555 ...` (no `connect`/`devices` round trip).
pub const SERIAL: &str = "127.0.0.1:5555";

/// `ADB = Path.home() / 'AppData/Local/Android/Sdk/platform-tools/adb.exe'`, as `str(ADB)`
/// prints it on Windows (backslashes). `Path.home()` = `%USERPROFILE%`.
pub fn adb_bin() -> String {
    let home = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")).unwrap_or_default();
    let mut p = PathBuf::from(home);
    for part in ["AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"] {
        p.push(part);
    }
    p.to_string_lossy().into_owned()
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EnvError(pub String);

impl std::fmt::Display for EnvError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for EnvError {}

/// The repo root (`.spectre/` lives there). Python derives it from `__file__`; the Rust binary
/// runs from an install path (E7), so `SPECTRE_REPO` is mandatory - no `current_exe()` guess.
pub fn repo_root() -> Result<PathBuf, EnvError> {
    repo_root_from(std::env::var_os("SPECTRE_REPO").map(PathBuf::from))
}

pub fn repo_root_from(v: Option<PathBuf>) -> Result<PathBuf, EnvError> {
    match v {
        Some(p) if !p.as_os_str().is_empty() => Ok(p),
        _ => Err(EnvError(
            "SPECTRE_REPO is not set: point it at the spectre checkout (holds .spectre/)".into(),
        )),
    }
}

/// The live gate's repo check: a typo'd or worktree `SPECTRE_REPO` must not create its own
/// `.spectre/afk-bot.lock` and tap past the real one. Requires `.spectre/` and
/// `scripts/_bot_lock.py`; returns the canonical path.
pub fn validate_repo(repo: &std::path::Path) -> Result<PathBuf, EnvError> {
    let canon = repo.canonicalize().map_err(|e| EnvError(format!("SPECTRE_REPO {}: {e}", repo.display())))?;
    if !canon.join(".spectre").is_dir() || !canon.join("scripts").join("_bot_lock.py").is_file() {
        return Err(EnvError(format!(
            "SPECTRE_REPO {} is not the bot checkout (needs .spectre/ and scripts/_bot_lock.py)",
            canon.display()
        )));
    }
    Ok(canon)
}

/// `TMP = REPO / '.spectre' / f'shots-{os.getpid()}'`.
pub fn shots_dir(repo: &std::path::Path, pid: u32) -> PathBuf {
    repo.join(".spectre").join(format!("shots-{pid}"))
}

/// `_env_tap_mode()`: `AFK_TAP_MODE` or `tap`; an unknown value warns and falls back.
/// Returns the mode and the WARN line Python prints (if any).
pub fn tap_mode_env(value: Option<&str>) -> (TapMode, Option<String>) {
    let mode = value.unwrap_or("tap");
    match TapMode::parse(mode) {
        Some(m) => (m, None),
        None => (TapMode::Tap, Some(format!("    WARN: AFK_TAP_MODE={} unknown -> tap", repr_str(mode)))),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repo_root_is_mandatory() {
        assert!(repo_root_from(None).unwrap_err().0.contains("SPECTRE_REPO"));
        assert!(repo_root_from(Some(PathBuf::new())).is_err());
        assert_eq!(repo_root_from(Some(PathBuf::from("C:/r"))).unwrap(), PathBuf::from("C:/r"));
    }

    #[test]
    fn validate_repo_needs_the_bot_checkout() {
        let d = std::env::temp_dir().join(format!("spectre-afk-repo-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("scripts")).unwrap();
        assert!(validate_repo(&d).unwrap_err().0.contains("not the bot checkout"));
        std::fs::create_dir_all(d.join(".spectre")).unwrap();
        std::fs::write(d.join("scripts").join("_bot_lock.py"), "").unwrap();
        assert!(validate_repo(&d).is_ok());
        assert!(validate_repo(&d.join("nope")).is_err());
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn tap_mode_env_like_python() {
        assert_eq!(tap_mode_env(None), (TapMode::Tap, None));
        assert_eq!(tap_mode_env(Some("sendevent")).0, TapMode::Sendevent);
        let (m, warn) = tap_mode_env(Some("bogus"));
        assert_eq!(m, TapMode::Tap);
        assert_eq!(warn.unwrap(), "    WARN: AFK_TAP_MODE='bogus' unknown -> tap");
    }

    #[test]
    fn adb_path_shape() {
        assert!(adb_bin().ends_with(r"AppData\Local\Android\Sdk\platform-tools\adb.exe") || cfg!(not(windows)));
        assert!(shots_dir(std::path::Path::new("R"), 42).ends_with("shots-42"));
    }
}
