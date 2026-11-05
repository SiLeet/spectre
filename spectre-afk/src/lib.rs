//! `spectre-afk` — Rust port of the AFK Journey bot (plan: `docs/reports/rust-port-plan.md`).
//!
//! E0b state: no bot code yet. [`testkit`] loads the frozen frame corpus
//! (`$SPECTRE_PARITY_DIR`, E0a) and the Python goldens (`parity/goldens`, E0b);
//! `tests/parity.rs` checks both and reports coverage (0 % until E1+ maps functions).

pub mod testkit;
