/// Spectre — umbrella crate re-exporting all spectre-* subcrates.
///
/// Use `use spectre::*;` to import everything from the entire workspace.
pub use spectre_core::*;
extern crate spectre_adb;
extern crate spectre_native;
extern crate spectre_game;
extern crate spectre_bot;
extern crate spectre_lua;