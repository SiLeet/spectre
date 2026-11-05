//! `spectre-afk` — Rust port of the AFK Journey bot (plan: `docs/reports/rust-port-plan.md`).
//!
//! E1 (android-infra): [`env`], [`infra`] (adb, tap modes, input sequences, screencap,
//! `Device`, trace), [`img`] (RGB frame, PNG), [`state::lock`] (pulled forward from E4),
//! [`pystr`]/[`hash`] (Python string semantics, SHA-256/CRC-32 without dependencies) and the
//! [`testkit`] (corpus/golden loader, FakeDevice, golden replay). Vision comes in E2.

pub mod env;
pub mod hash;
pub mod img;
pub mod infra;
pub mod pystr;
pub mod state;
pub mod testkit;
