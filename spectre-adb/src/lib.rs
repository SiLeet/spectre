/// Multi-device discovery and orchestration (`AdbManager`).
pub mod multi;
pub mod process;
/// Spectre ADB — process memory reading over Android Debug Bridge.
pub mod reader;

pub use multi::{adb_path, AdbDevice, AdbManager, parse_adb_devices, reader_for_serial};
pub use reader::AdbReader;
