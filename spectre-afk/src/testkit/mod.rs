//! Parity testkit (rust-port-plan §4): corpus frames and golden JSONL files, the test
//! doubles of `scripts/tests/fake_vision.py` ([`fake`]) and the golden replay ([`replay`]).

pub mod fake;
pub mod replay;

pub use crate::hash::crc32;
pub use crate::img::{Frame, load_rgb};

use anyhow::{Context, Result, bail};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{BufRead, BufReader, Read};
use std::sync::OnceLock;
use std::path::{Path, PathBuf};

/// Default corpus location (E0a); override with `SPECTRE_PARITY_DIR`.
pub const DEFAULT_PARITY_DIR: &str = "C:/Users/Sigi/spectre-parity";

/// Corpus root (`frames/`, `synthetic/`), outside every repo.
pub fn parity_dir() -> PathBuf {
    std::env::var_os("SPECTRE_PARITY_DIR").map_or_else(|| PathBuf::from(DEFAULT_PARITY_DIR), PathBuf::from)
}

/// Committed manifests and goldens: `<repo>/parity`.
pub fn repo_parity() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("parity")
}

/// `SPECTRE_PARITY=1`: missing corpus/goldens fail instead of skipping (§4.4).
pub fn strict() -> bool {
    std::env::var("SPECTRE_PARITY").is_ok_and(|v| v == "1")
}

/// Width/height from the IHDR chunk without decoding pixels.
pub fn png_dims(path: &Path) -> Result<(u32, u32)> {
    let mut head = [0u8; 24];
    File::open(path)
        .and_then(|mut f| f.read_exact(&mut head))
        .with_context(|| format!("read {}", path.display()))?;
    if &head[..8] != b"\x89PNG\r\n\x1a\n" || &head[12..16] != b"IHDR" {
        bail!("{}: not a PNG", path.display());
    }
    let be = |b: &[u8]| u32::from_be_bytes([b[0], b[1], b[2], b[3]]);
    Ok((be(&head[16..20]), be(&head[20..24])))
}

/// One corpus entry of `parity/frames.json`.
#[derive(Debug, Clone)]
pub struct CorpusFrame {
    pub w: u32,
    pub h: u32,
    pub mode: String,
    pub crc32: Option<u32>,
    pub alpha_min: Option<u8>,
}

/// One golden file: `{"header": …}` line, then one record per line.
#[derive(Debug)]
pub struct Golden {
    pub header: Value,
    pub rows: Vec<Value>,
}

pub fn load_jsonl(path: &Path) -> Result<Golden> {
    let f = File::open(path).with_context(|| format!("open {}", path.display()))?;
    let mut lines = BufReader::new(f).lines();
    let first = lines.next().context("empty golden")??;
    let header = serde_json::from_str::<Value>(&first)?
        .get("header")
        .cloned()
        .with_context(|| format!("{}: first line has no header", path.display()))?;
    let mut rows = Vec::new();
    for (i, line) in lines.enumerate() {
        let line = line?;
        rows.push(serde_json::from_str(&line).with_context(|| format!("{}:{}", path.display(), i + 2))?);
    }
    Ok(Golden { header, rows })
}

/// sha16 → entry for every corpus frame in `parity/frames.json`.
pub fn corpus_manifest(path: &Path) -> Result<BTreeMap<String, CorpusFrame>> {
    let v: Value = serde_json::from_reader(BufReader::new(File::open(path)?))?;
    let mut out = BTreeMap::new();
    for e in v["frames"].as_array().context("frames.json: no frames")? {
        let num = |k: &str| e[k].as_u64().and_then(|n| u32::try_from(n).ok());
        out.insert(
            e["sha16"].as_str().context("sha16")?.to_owned(),
            CorpusFrame {
                w: num("w").context("w")?,
                h: num("h").context("h")?,
                mode: e["mode"].as_str().unwrap_or("?").to_owned(),
                crc32: num("crc32"),
                alpha_min: e["alpha_min"].as_u64().and_then(|n| u8::try_from(n).ok()),
            },
        );
    }
    Ok(out)
}

/// Current Python tree pin, the same definition as `export_goldens.py py_tree()`: sha16 over
/// `git ls-tree -r HEAD -- scripts templates` without `scripts/tests/parity/`. `None` if git
/// is unavailable.
pub fn current_py_tree() -> Option<String> {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
    let out = std::process::Command::new("git")
        .arg("-C")
        .arg(&repo)
        .args(["ls-tree", "-r", "HEAD", "--", "scripts", "templates"])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&out.stdout);
    let lines: Vec<&str> = crate::pystr::splitlines(&text)
        .into_iter()
        .filter(|l| !l.split_once('\t').is_some_and(|(_, p)| p.starts_with("scripts/tests/parity/")))
        .collect();
    Some(crate::hash::sha16(&[lines.join("\n").as_bytes()]))
}

/// A frame by its golden key: corpus `frames/<k>.png`, a synthetic alias (`convert('RGB')` of
/// a corpus frame = [`load_rgb`]) or `synthetic/<k>.png`.
pub fn frame_by_key(key: &str) -> Result<Frame> {
    static SYNTH: OnceLock<Value> = OnceLock::new();
    let synth = SYNTH.get_or_init(|| {
        std::fs::read_to_string(repo_parity().join("goldens").join("synthetic.json"))
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or(Value::Null)
    });
    let corpus = parity_dir().join("frames").join(format!("{key}.png"));
    if corpus.is_file() {
        return Ok(load_rgb(&corpus)?);
    }
    if let Some(alias) = synth["frames"][key]["alias_of"].as_str() {
        return Ok(load_rgb(&parity_dir().join("frames").join(format!("{alias}.png")))?);
    }
    let p = parity_dir().join("synthetic").join(format!("{key}.png"));
    load_rgb(&p).with_context(|| format!("frame {key} in neither corpus nor synthetic"))
}

/// Every frame key (`{"img": k}` or `"frame": k`) referenced in a golden value.
pub fn frame_refs(v: &Value, out: &mut Vec<String>) {
    match v {
        Value::Object(m) => {
            for (k, x) in m {
                match (k.as_str(), x) {
                    ("img" | "frame", Value::String(s)) => out.push(s.clone()),
                    _ => frame_refs(x, out),
                }
            }
        }
        Value::Array(a) => a.iter().for_each(|x| frame_refs(x, out)),
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frame_refs_finds_nested_keys() {
        let v: Value = serde_json::json!({"args": [{"img": "aa"}, [1, {"img": "bb"}]],
                                          "events": [{"ev": "shot", "frame": "cc"}, {"ev": "tap", "x": 1}]});
        let mut out = Vec::new();
        frame_refs(&v, &mut out);
        assert_eq!(out, ["aa", "bb", "cc"]);
    }

    #[test]
    fn png_round_trip_rgb_and_gray() {
        let dir = std::env::temp_dir().join(format!("spectre-afk-testkit-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        for (ct, px, want) in [
            (png::ColorType::Rgb, vec![1u8, 2, 3, 4, 5, 6], vec![1u8, 2, 3, 4, 5, 6]),
            (png::ColorType::Rgba, vec![1, 2, 3, 9, 4, 5, 6, 9], vec![1, 2, 3, 4, 5, 6]),
            (png::ColorType::Grayscale, vec![7, 8], vec![7, 7, 7, 8, 8, 8]),
        ] {
            let p = dir.join(format!("{ct:?}.png"));
            let mut enc = png::Encoder::new(std::io::BufWriter::new(File::create(&p).unwrap()), 2, 1);
            enc.set_color(ct);
            enc.set_depth(png::BitDepth::Eight);
            enc.write_header().unwrap().write_image_data(&px).unwrap();
            assert_eq!(png_dims(&p).unwrap(), (2, 1));
            assert_eq!(load_rgb(&p).unwrap(), Frame { w: 2, h: 1, rgb: want });
        }
        std::fs::remove_dir_all(&dir).ok();
    }
}
