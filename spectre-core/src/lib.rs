/// Spectre Core — types, traits, and scan engine for game memory analysis.
pub mod diff;
pub mod dump_reader;
pub mod error;
pub mod reader;
pub mod scanner;
pub mod types;

pub use diff::{ChangedRegion, DEFAULT_MERGE_GAP, DumpDiff, diff_dumps, diff_dumps_with_gap};
pub use dump_reader::DumpFileReader;
pub use error::SpectreError;
pub use reader::MemoryReader;
pub use scanner::{scan_memory, ScanConfig};
pub use types::*;