/// Error types for Spectre operations.
use std::fmt;

/// The central error type for the whole framework.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SpectreError {
    ProcessNotFound(String),
    PermissionDenied(String),
    ReadError { pid: u32, address: u64, msg: String },
    WriteError { pid: u32, address: u64, msg: String },
    BackendError(String),
    ConfigError(String),
    ScriptError(String),
    Timeout(String),
}

impl fmt::Display for SpectreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SpectreError::ProcessNotFound(p) => write!(f, "process not found: {p}"),
            SpectreError::PermissionDenied(reason) => write!(f, "permission denied: {reason}"),
            SpectreError::ReadError { pid, address, msg } => {
                write!(f, "read error (pid={pid}, address={address:#x}): {msg}")
            }
            SpectreError::WriteError { pid, address, msg } => {
                write!(f, "write error (pid={pid}, address={address:#x}): {msg}")
            }
            SpectreError::BackendError(msg) => write!(f, "backend error: {msg}"),
            SpectreError::ConfigError(msg) => write!(f, "configuration error: {msg}"),
            SpectreError::ScriptError(msg) => write!(f, "script error: {msg}"),
            SpectreError::Timeout(msg) => write!(f, "timeout: {msg}"),
        }
    }
}

impl std::error::Error for SpectreError {}