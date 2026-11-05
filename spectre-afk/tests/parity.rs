//! E0b parity gate (rust-port-plan §4.4).
//!
//! Plain `cargo test`: missing corpus/goldens → loud skip with counts; the first
//! frames are decoded and checked against their Pillow CRC.
//! `SPECTRE_PARITY=1`: every frame is decoded and must match Pillow's
//! `convert('RGB')` bytes (CRC-32); missing frames, transparent frames, STALE
//! or dirty goldens FAIL. Unknown frame keys and mixed Python trees always FAIL.
//! No py-fn is mapped yet (E1+), so coverage starts at 0 %.

use spectre_afk::testkit::{
    self, corpus_manifest, crc32, current_py_tree, frame_refs, load_jsonl, load_rgb, png_dims, strict,
};
use std::collections::{BTreeMap, BTreeSet};

/// py-fn names already ported to Rust. Filled stage by stage (E1+); empty in E0b.
const DISPATCH: &[&str] = &[];
/// Frames fully decoded outside strict mode (debug builds decode slowly).
const QUICK_DECODES: usize = 3;

fn skip(what: &str) {
    assert!(!strict(), "SPECTRE_PARITY=1 but {what}");
    eprintln!("PARITY SKIP: {what}");
}

#[test]
fn corpus_frames_match_manifest() {
    let manifest = testkit::repo_parity().join("frames.json");
    let frames_dir = testkit::parity_dir().join("frames");
    if !manifest.is_file() || !frames_dir.is_dir() {
        return skip(&format!("no corpus ({} / {})", manifest.display(), frames_dir.display()));
    }
    let frames = corpus_manifest(&manifest).unwrap();
    let (mut missing, mut bad, mut decoded) = (Vec::new(), Vec::new(), 0usize);
    for (key, f) in &frames {
        let p = frames_dir.join(format!("{key}.png"));
        if !p.is_file() {
            missing.push(key.clone());
            continue;
        }
        match png_dims(&p) {
            Ok(d) if d == (f.w, f.h) => {}
            other => bad.push(format!("{key}: dims {other:?} != ({}, {})", f.w, f.h)),
        }
        if f.alpha_min.is_some_and(|a| a < 255) {
            bad.push(format!("{key}: alpha_min {:?} (RGBA ops not ported)", f.alpha_min));
        }
        if strict() || decoded < QUICK_DECODES {
            let img = load_rgb(&p).unwrap();
            decoded += 1;
            if img.rgb.len() != f.w as usize * f.h as usize * 3 {
                bad.push(format!("{key}: {} RGB bytes", img.rgb.len()));
            } else if f.crc32.is_some_and(|c| c != crc32(&img.rgb)) {
                bad.push(format!("{key} ({}): decoded pixels differ from Pillow convert('RGB')", f.mode));
            }
        }
    }
    eprintln!(
        "corpus: {} frames, {decoded} decoded, {} missing, {} bad",
        frames.len(),
        missing.len(),
        bad.len()
    );
    assert!(bad.is_empty(), "corpus mismatches: {bad:?}");
    if !missing.is_empty() {
        skip(&format!("{} corpus frames missing, first {:?}", missing.len(), &missing[..missing.len().min(5)]));
    }
}

#[test]
fn goldens_load_and_report_coverage() {
    let root = testkit::repo_parity();
    let goldens = root.join("goldens");
    if !goldens.is_dir() {
        return skip(&format!("no goldens at {}", goldens.display()));
    }
    let mut known: BTreeSet<String> = match corpus_manifest(&root.join("frames.json")) {
        Ok(m) => m.into_keys().collect(),
        Err(e) => return skip(&format!("frames.json: {e:#}")),
    };
    let synth: serde_json::Value = match std::fs::read_to_string(goldens.join("synthetic.json"))
        .map_err(anyhow::Error::from)
        .and_then(|s| Ok(serde_json::from_str(&s)?))
    {
        Ok(v) => v,
        Err(e) => return skip(&format!("synthetic.json: {e:#}")),
    };
    known.extend(synth["frames"].as_object().into_iter().flat_map(|m| m.keys().cloned()));

    let mut fns: BTreeMap<String, usize> = BTreeMap::new();
    let (mut records, mut unknown, mut py_tree, mut dirty) = (0usize, BTreeSet::new(), BTreeSet::new(), false);
    for kind in ["calls", "flows"] {
        let Ok(rd) = std::fs::read_dir(goldens.join(kind)) else { continue };
        for entry in rd {
            let path = entry.unwrap().path();
            let g = load_jsonl(&path).unwrap();
            py_tree.insert(g.header["py_tree"].as_str().expect("header.py_tree").to_owned());
            dirty |= g.header.get("dirty").is_some();
            assert!(g.header["pillow"].is_string(), "{}: header.pillow", path.display());
            for row in &g.rows {
                records += 1;
                if kind == "calls" {
                    *fns.entry(row["fn"].as_str().unwrap_or("?").to_owned()).or_default() += 1;
                }
                let mut refs = Vec::new();
                frame_refs(row, &mut refs);
                unknown.extend(refs.into_iter().filter(|k| !known.contains(k)));
            }
        }
    }
    if records == 0 {
        return skip("no golden records");
    }
    assert_eq!(py_tree.len(), 1, "goldens from more than one Python tree: {py_tree:?}");
    assert!(unknown.is_empty(), "frame keys in no manifest: {unknown:?}");
    let pinned = py_tree.into_iter().next().unwrap_or_default();
    match current_py_tree() {
        Some(now) if now == pinned => {}
        Some(now) => skip(&format!("STALE goldens: py_tree {pinned}, scripts/+templates/ now {now}")),
        None => skip("py_tree unknown (python/git unavailable): STALE not checked"),
    }
    if dirty {
        skip("goldens were exported from a dirty tree (--allow-dirty)");
    }

    let mut per_mod: BTreeMap<&str, (usize, usize)> = BTreeMap::new();
    for f in fns.keys() {
        let e = per_mod.entry(f.split('.').next().unwrap_or("?")).or_default();
        e.1 += 1;
        if DISPATCH.contains(&f.as_str()) {
            e.0 += 1;
        }
    }
    eprintln!("goldens: {records} records, {} distinct call fns, py_tree {pinned}", fns.len());
    for (m, (ported, total)) in &per_mod {
        eprintln!("  coverage {m}: {ported}/{total} fns ported");
    }
    // shortcut: no parity/scope/E<n>.toml yet, so unported fns are reported, not failed (E1 adds scopes)
    let unported = fns.keys().filter(|f| !DISPATCH.contains(&f.as_str())).count();
    eprintln!("PARITY: {unported} unported fns (expected in E0b)");
}
