//! Parity testkit (rust-port-plan §4): corpus frames and golden JSONL files.

use anyhow::{Context, Result, bail};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};

/// Default corpus location (E0a); override with `SPECTRE_PARITY_DIR`.
pub const DEFAULT_PARITY_DIR: &str = "C:/Users/Sigi/spectre-parity";

/// An RGB frame as Pillow's `convert('RGB')` yields it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub w: u32,
    pub h: u32,
    pub rgb: Vec<u8>,
}

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

/// Decode a corpus PNG to RGB the way Pillow's `convert('RGB')` does for
/// 8-bit images: alpha dropped, gray replicated, palette expanded.
pub fn load_rgb(path: &Path) -> Result<Frame> {
    let file = File::open(path).with_context(|| format!("open {}", path.display()))?;
    let mut dec = png::Decoder::new(BufReader::new(file));
    dec.set_transformations(png::Transformations::EXPAND);
    let mut reader = dec.read_info().with_context(|| format!("decode {}", path.display()))?;
    let (ct, depth) = reader.output_color_type();
    if depth != png::BitDepth::Eight {
        bail!("{}: {depth:?}-bit output not ported (Pillow I;16 semantics)", path.display());
    }
    let mut buf = vec![0; reader.output_buffer_size().context("buffer size")?];
    let info = reader.next_frame(&mut buf)?;
    let px = &buf[..info.buffer_size()];
    let rgb = match ct {
        png::ColorType::Rgb => px.to_vec(),
        png::ColorType::Rgba => px.as_chunks::<4>().0.iter().flat_map(|p| [p[0], p[1], p[2]]).collect(),
        png::ColorType::Grayscale => px.iter().flat_map(|&g| [g, g, g]).collect(),
        png::ColorType::GrayscaleAlpha => px.as_chunks::<2>().0.iter().flat_map(|p| [p[0], p[0], p[0]]).collect(),
        png::ColorType::Indexed => bail!("{}: palette not expanded", path.display()),
    };
    Ok(Frame { w: info.width, h: info.height, rgb })
}

/// CRC-32 (IEEE, as Python's `zlib.crc32`) of a byte slice; checks decoded pixels
/// against `frames.json` without a hash-crate dependency.
pub fn crc32(data: &[u8]) -> u32 {
    let mut table = [0u32; 256];
    for (i, slot) in table.iter_mut().enumerate() {
        let mut c = i as u32;
        for _ in 0..8 {
            c = if c & 1 == 1 { 0xEDB8_8320 ^ (c >> 1) } else { c >> 1 };
        }
        *slot = c;
    }
    !data.iter().fold(!0u32, |c, &b| table[((c ^ u32::from(b)) & 0xFF) as usize] ^ (c >> 8))
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

/// Current Python tree pin, computed by the exporter (`export_goldens.py py-tree`)
/// so Rust and Python share one definition. `None` if python/git are unavailable.
pub fn current_py_tree() -> Option<String> {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("..");
    let script = repo.join("scripts/tests/parity/export_goldens.py");
    let out = std::process::Command::new("python")
        .arg(&script)
        .args(["py-tree", "--repo"])
        .arg(&repo)
        .output()
        .ok()?;
    out.status.success().then(|| String::from_utf8_lossy(&out.stdout).trim().to_owned())
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
    fn crc32_matches_zlib() {
        assert_eq!(crc32(b""), 0);
        assert_eq!(crc32(b"123456789"), 0xCBF4_3926); // zlib.crc32(b"123456789")
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
