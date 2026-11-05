//! Everything between the bot and `adb.exe` (rust-port-plan §E1), ported 1:1 from
//! `afk_claim_vision.py` L486-L734. Python's module globals (`adb`, `tap`, `TAP_MODE`, ...)
//! become the [`device::Device`] trait: its high-level methods default to the free
//! functions here, and every implementation (real adb, test fakes, golden replay) may
//! override single methods - exactly the seams the Python tests patch.

pub mod adb;
pub mod clock;
pub mod device;
pub mod screencap;
pub mod seq;
pub mod tap;
pub mod trace;

use spectre_mcp::RunError;

/// The exceptions the Python infra raises (and the replay compares by name).
#[derive(Debug, Clone, PartialEq)]
pub enum InfraError {
    /// `RuntimeError` (adb rc != 0 on a non-tolerated step, screencap failed).
    Runtime(String),
    /// `subprocess.TimeoutExpired` from an adb call.
    Timeout,
    /// `OSError` (adb.exe missing, file I/O).
    Os(String),
    /// Image decode/encode failure (Pillow: `UnidentifiedImageError` / `OSError`).
    Img(String),
    /// A test guard fired (`test.fail` in Python: unscripted shot, keyevent 4 on WORLD, real adb).
    Fail(String),
}

impl InfraError {
    /// Python exception class name, as the goldens record it.
    pub fn py_type(&self) -> &'static str {
        match self {
            InfraError::Runtime(_) => "RuntimeError",
            InfraError::Timeout => "TimeoutExpired",
            InfraError::Os(_) => "OSError",
            InfraError::Img(_) => "UnidentifiedImageError",
            InfraError::Fail(_) => "AssertionError",
        }
    }

    pub fn from_py_type(name: &str, msg: &str) -> Self {
        match name {
            "RuntimeError" => InfraError::Runtime(msg.into()),
            "TimeoutExpired" => InfraError::Timeout,
            "OSError" | "FileNotFoundError" | "PermissionError" => InfraError::Os(msg.into()),
            "UnidentifiedImageError" => InfraError::Img(msg.into()),
            other => InfraError::Fail(format!("{other}: {msg}")),
        }
    }
}

impl From<RunError> for InfraError {
    fn from(e: RunError) -> Self {
        match e {
            RunError::Timeout => InfraError::Timeout,
            RunError::Spawn(m) => InfraError::Os(m),
        }
    }
}

impl From<crate::img::ImgError> for InfraError {
    fn from(e: crate::img::ImgError) -> Self {
        match e {
            crate::img::ImgError::Io(e) => InfraError::Os(e.to_string()),
            crate::img::ImgError::Png(m) => InfraError::Img(m),
        }
    }
}

impl std::fmt::Display for InfraError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            InfraError::Runtime(m) | InfraError::Os(m) | InfraError::Img(m) | InfraError::Fail(m) => f.write_str(m),
            InfraError::Timeout => f.write_str("adb timed out"),
        }
    }
}

impl std::error::Error for InfraError {}

pub type Result<T> = std::result::Result<T, InfraError>;
