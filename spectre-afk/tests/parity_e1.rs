//! E1 parity (rust-port-plan §E1 exit 1-3): every recorded direct call into the Python infra
//! (`parity/goldens/infra/*.jsonl`) is replayed against the Rust port - argv sequences incl.
//! sendevent batches and the tap -> touchscreen -> sendevent fallback with `_TAP_DEAD`,
//! timeouts, sleeps, results, exceptions and the tap state afterwards.
//!
//! Plain `cargo test`: no infra goldens -> loud skip; any Diff fails. `SPECTRE_PARITY=1`:
//! unsupported records, a skip or STALE goldens fail as well (§4.4: 0 Fails, 0 Skips, 0 STALE).

use spectre_afk::testkit::replay::{Outcome, replay_lock, replay_vision, stdout_diff};
use spectre_afk::testkit::{current_py_tree, load_jsonl, repo_parity, strict};
use std::collections::BTreeMap;

fn skip(what: &str) {
    assert!(!strict(), "SPECTRE_PARITY=1 but {what}");
    eprintln!("PARITY SKIP: {what}");
}

/// `key = ["a", "b"]` lists of parity/scope/E1.toml (no toml dependency for three flat lists).
fn scope_list(text: &str, key: &str) -> Vec<String> {
    let Some(line) = text.lines().find(|l| l.trim_start().starts_with(&format!("{key} ="))) else { return vec![] };
    line.split_once('=').map(|(_, v)| v).unwrap_or("").split('"').skip(1).step_by(2).map(str::to_owned).collect()
}

#[test]
fn e1_infra_records_replay_identically() {
    let dir = repo_parity().join("goldens").join("infra");
    let scope = std::fs::read_to_string(repo_parity().join("scope").join("E1.toml")).expect("parity/scope/E1.toml");
    let shards = scope_list(&scope, "shards");
    let modules = scope_list(&scope, "modules");
    if !shards.iter().all(|f| dir.join(format!("{f}.jsonl")).is_file()) {
        return skip(&format!("no infra goldens in {}", dir.display()));
    }
    let unknown: Vec<String> = std::fs::read_dir(&dir)
        .unwrap()
        .filter_map(|e| e.ok()?.path().file_stem()?.to_str().map(str::to_owned))
        .filter(|s| !shards.contains(s))
        .collect();
    assert!(unknown.is_empty(), "infra shards outside parity/scope/E1.toml: {unknown:?}");

    let mut per_fn: BTreeMap<String, [usize; 3]> = BTreeMap::new(); // pass, diff, unsupported
    let mut per_module: BTreeMap<String, usize> = modules.iter().map(|m| (m.clone(), 0)).collect();
    let (mut diffs, mut unsupported, mut stdout_info) = (Vec::new(), Vec::new(), Vec::new());
    let mut trees = std::collections::BTreeSet::new();
    let mut events = 0usize;
    for f in &shards {
        let g = load_jsonl(&dir.join(format!("{f}.jsonl"))).unwrap();
        trees.insert(g.header["py_tree"].as_str().unwrap_or("?").to_owned());
        for rec in &g.rows {
            let name = rec["fn"].as_str().unwrap_or("?").to_owned();
            let test = rec["test"].as_str().unwrap_or("?");
            // identical calls from several tests are one record listing every test (`tests`)
            let mods: std::collections::BTreeSet<String> = rec["tests"]
                .as_array()
                .map(|a| a.iter().filter_map(|t| t.as_str()).map(|t| t.split('.').next().unwrap_or("?").to_owned()).collect())
                .unwrap_or_else(|| [test.split('.').next().unwrap_or("?").to_owned()].into());
            for m in mods {
                *per_module.entry(m).or_default() += 1;
            }
            events += rec["events"].as_array().map_or(0, Vec::len);
            let mut log = Vec::new();
            let outcome = if f == "_bot_lock" { replay_lock(rec) } else { replay_vision(rec, &mut log) };
            if f != "_bot_lock"
                && outcome == Outcome::Pass
                && let Some(d) = stdout_diff(rec, &log)
            {
                stdout_info.push(format!("{name} [{test}]: {d}"));
            }
            let slot = per_fn.entry(name.clone()).or_default();
            match outcome {
                Outcome::Pass => slot[0] += 1,
                Outcome::Diff(d) => {
                    slot[1] += 1;
                    diffs.push(format!("{name} [{test}]: {}", d.join(" | ")));
                }
                Outcome::Unsupported(why) => {
                    slot[2] += 1;
                    unsupported.push(format!("{name} [{test}]: {why}"));
                }
            }
        }
    }
    let total: [usize; 3] = per_fn.values().fold([0; 3], |a, b| [a[0] + b[0], a[1] + b[1], a[2] + b[2]]);
    eprintln!("E1 infra records: {} pass, {} diff, {} unsupported ({events} recorded events replayed)", total[0], total[1], total[2]);
    for (name, [p, d, u]) in &per_fn {
        eprintln!("  {name:40} pass {p:3}  diff {d:3}  unsupported {u:3}");
    }
    for (m, n) in &per_module {
        eprintln!("  module {m:32} {n:3} records{}", if modules.contains(m) { "" } else { "  (not in scope list)" });
    }
    for u in &unsupported {
        eprintln!("UNSUPPORTED {u}");
    }
    for d in &diffs {
        eprintln!("DIFF {d}");
    }
    for s in &stdout_info {
        eprintln!("STDOUT (informative) {s}");
    }
    eprintln!("stdout: {} of {} replayed calls print differently (informative, §4.3)", stdout_info.len(), total[0]);
    assert_eq!(trees.len(), 1, "infra goldens from more than one Python tree: {trees:?}");
    let pinned = trees.into_iter().next().unwrap_or_default();
    match current_py_tree() {
        Some(now) if now == pinned => {}
        Some(now) => skip(&format!("STALE infra goldens: py_tree {pinned}, scripts/+templates/ now {now}")),
        None => skip("py_tree unknown (git unavailable): STALE not checked"),
    }
    assert!(diffs.is_empty(), "{} E1 records differ (see DIFF lines)", diffs.len());
    let empty: Vec<&String> = modules.iter().filter(|m| per_module.get(*m) == Some(&0)).collect();
    if !empty.is_empty() {
        skip(&format!("scope modules without any infra record: {empty:?}"));
    }
    if !unsupported.is_empty() {
        skip(&format!("{} E1 records not replayable (see UNSUPPORTED lines)", unsupported.len()));
    }
    assert!(total[0] > 0, "no E1 record replayed");
}

/// Lock interop with the real `_bot_lock.py` in both directions (plan §E1 tests).
#[test]
fn lock_interop_with_python() {
    use spectre_afk::state::lock;
    let repo = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
    let dir = std::env::temp_dir().join(format!("spectre-afk-interop-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("afk-bot.lock");
    let py = |code: &str| -> Option<String> {
        let full = format!(
            "import sys; sys.path.insert(0, r'{}'); import _bot_lock as b; from pathlib import Path; L = Path(r'{}'); env = {{}}\n{code}",
            repo.join("scripts").display(),
            path.display()
        );
        let out = std::process::Command::new("python").args(["-c", &full]).output().ok()?;
        out.status.success().then(|| String::from_utf8_lossy(&out.stdout).trim().to_owned())
    };
    let Some(py_pid) = py("print(b.acquire(L, env), __import__('os').getpid())") else {
        return skip("python unavailable: lock interop not checked");
    };
    // Python created it -> Rust sees a fresh foreign lock
    let owner = py_pid.split_whitespace().nth(1).unwrap().to_owned();
    assert!(py_pid.starts_with("True"), "{py_pid}");
    assert_eq!(std::fs::read_to_string(&path).unwrap(), owner);
    let no_env = |_: &str| None;
    let me = std::process::id();
    assert!(!lock::acquire(&path, &no_env, None, None, me).unwrap());
    assert!(lock::describe(&path, None).unwrap().starts_with(&format!("pid {owner}, age ")));
    lock::release(&path, &no_env, me).unwrap(); // not ours: kept
    assert!(path.exists());
    // Rust takes over (stale) -> Python sees a fresh foreign lock and keeps it on release
    assert!(lock::acquire(&path, &no_env, None, Some(4_000_000_000.0), me).unwrap());
    assert_eq!(std::fs::read_to_string(&path).unwrap(), me.to_string());
    assert_eq!(py("print(b.acquire(L, env))").as_deref(), Some("False"));
    assert_eq!(py("b.release(L, env); print(L.exists())").as_deref(), Some("True"));
    assert_eq!(py("print(b.describe(L).split(',')[0])").as_deref(), Some(format!("pid {me}").as_str()));
    // inherited wrapper lock: Python leaves the file alone; Rust releases its own
    assert_eq!(py("print(b.acquire(L, {'AFK_BOT_LOCK_HELD': '1'}))").as_deref(), Some("True"));
    lock::release(&path, &no_env, me).unwrap();
    assert!(!path.exists());
    let _ = std::fs::remove_dir_all(&dir);
}
