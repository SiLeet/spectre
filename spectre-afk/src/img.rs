//! Minimal image core for E1 (rust-port-plan §2.2 `img/frame.rs`, `png_io.rs`): an RGB
//! frame as Pillow's `convert('RGB')` yields it, PIL-compatible crop, PNG in/out.
//! Vision (avg, resize, ...) comes in E2.

use crate::hash::{crc32, sha16};
use std::fs::File;
use std::io::{BufReader, BufWriter, Cursor};
use std::path::Path;

/// RGB, row-major, 3 bytes per pixel.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Frame {
    pub w: u32,
    pub h: u32,
    pub rgb: Vec<u8>,
}

impl Frame {
    pub fn new(w: u32, h: u32, rgb: Vec<u8>) -> Self {
        assert_eq!(rgb.len(), w as usize * h as usize * 3, "RGB buffer size");
        Self { w, h, rgb }
    }

    pub fn pixel(&self, x: u32, y: u32) -> [u8; 3] {
        let i = (y as usize * self.w as usize + x as usize) * 3;
        [self.rgb[i], self.rgb[i + 1], self.rgb[i + 2]]
    }

    /// `img.crop((l, t, r, b))`: area outside the frame reads as black, like Pillow.
    pub fn crop(&self, l: i64, t: i64, r: i64, b: i64) -> Frame {
        let (cw, ch) = ((r - l).max(0) as u32, (b - t).max(0) as u32);
        let mut out = vec![0u8; cw as usize * ch as usize * 3];
        for y in 0..ch as i64 {
            let sy = t + y;
            if sy < 0 || sy >= self.h as i64 {
                continue;
            }
            for x in 0..cw as i64 {
                let sx = l + x;
                if sx < 0 || sx >= self.w as i64 {
                    continue;
                }
                let s = (sy as usize * self.w as usize + sx as usize) * 3;
                let d = (y as usize * cw as usize + x as usize) * 3;
                out[d..d + 3].copy_from_slice(&self.rgb[s..s + 3]);
            }
        }
        Frame::new(cw, ch, out)
    }

    /// The corpus/golden key of this frame as an RGB image (`freeze_corpus.frame_key`).
    pub fn key(&self) -> String {
        sha16(&[format!("RGB|{}x{}|", self.w, self.h).as_bytes(), &self.rgb])
    }

    pub fn crc32(&self) -> u32 {
        crc32(&self.rgb)
    }
}

#[derive(Debug)]
pub enum ImgError {
    Io(std::io::Error),
    Png(String),
}

impl std::fmt::Display for ImgError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ImgError::Io(e) => write!(f, "{e}"),
            ImgError::Png(e) => write!(f, "PNG: {e}"),
        }
    }
}

impl std::error::Error for ImgError {}

impl From<std::io::Error> for ImgError {
    fn from(e: std::io::Error) -> Self {
        ImgError::Io(e)
    }
}

/// Decode a PNG to RGB the way Pillow's `convert('RGB')` does for 8-bit images:
/// alpha dropped, gray replicated, palette expanded.
pub fn decode_png<R: std::io::BufRead + std::io::Seek>(r: R) -> Result<Frame, ImgError> {
    let mut dec = png::Decoder::new(r);
    dec.set_transformations(png::Transformations::EXPAND);
    let mut reader = dec.read_info().map_err(|e| ImgError::Png(e.to_string()))?;
    let (ct, depth) = reader.output_color_type();
    if depth != png::BitDepth::Eight {
        return Err(ImgError::Png(format!("{depth:?}-bit output not ported (Pillow I;16 semantics)")));
    }
    let size = reader.output_buffer_size().ok_or_else(|| ImgError::Png("buffer size".into()))?;
    let mut buf = vec![0; size];
    let info = reader.next_frame(&mut buf).map_err(|e| ImgError::Png(e.to_string()))?;
    let px = &buf[..info.buffer_size()];
    let rgb = match ct {
        png::ColorType::Rgb => px.to_vec(),
        png::ColorType::Rgba => px.as_chunks::<4>().0.iter().flat_map(|p| [p[0], p[1], p[2]]).collect(),
        png::ColorType::Grayscale => px.iter().flat_map(|&g| [g, g, g]).collect(),
        png::ColorType::GrayscaleAlpha => px.as_chunks::<2>().0.iter().flat_map(|p| [p[0], p[0], p[0]]).collect(),
        png::ColorType::Indexed => return Err(ImgError::Png("palette not expanded".into())),
    };
    Ok(Frame::new(info.width, info.height, rgb))
}

pub fn decode_png_bytes(data: &[u8]) -> Result<Frame, ImgError> {
    decode_png(Cursor::new(data))
}

pub fn load_rgb(path: &Path) -> Result<Frame, ImgError> {
    decode_png(BufReader::new(File::open(path)?))
}

/// `img.save(path, compress_level=1)`: 8-bit RGB, chunks IHDR/IDAT/IEND only (no gAMA/sRGB/
/// iCCP/cHRM/pHYs, like Pillow without info). Only the pixels have to match Python.
pub fn save_png(frame: &Frame, path: &Path) -> Result<(), ImgError> {
    let mut enc = png::Encoder::new(BufWriter::new(File::create(path)?), frame.w, frame.h);
    enc.set_color(png::ColorType::Rgb);
    enc.set_depth(png::BitDepth::Eight);
    enc.set_compression(png::Compression::Fast);
    let mut w = enc.write_header().map_err(|e| ImgError::Png(e.to_string()))?;
    w.write_image_data(&frame.rgb).map_err(|e| ImgError::Png(e.to_string()))?;
    w.finish().map_err(|e| ImgError::Png(e.to_string()))
}

/// Chunk types of a PNG file in order (for the IHDR/IDAT/IEND contract).
pub fn png_chunks(data: &[u8]) -> Vec<String> {
    let mut out = Vec::new();
    let mut i = 8;
    while i + 8 <= data.len() {
        let len = u32::from_be_bytes([data[i], data[i + 1], data[i + 2], data[i + 3]]) as usize;
        out.push(String::from_utf8_lossy(&data[i + 4..i + 8]).into_owned());
        i += 12 + len;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crop_pads_black_like_pillow() {
        let f = Frame::new(2, 2, vec![1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4]);
        let c = f.crop(-1, 0, 2, 1);
        assert_eq!((c.w, c.h), (3, 1));
        assert_eq!(c.rgb, [0, 0, 0, 1, 1, 1, 2, 2, 2]);
        assert_eq!(f.crop(1, 1, 1, 3).w, 0);
    }

    #[test]
    fn key_matches_python_frame_key() {
        // python: freeze_corpus.frame_key(Image.new('RGB', (1, 1), (0, 0, 0)))
        let f = Frame::new(1, 1, vec![0, 0, 0]);
        assert_eq!(f.key(), crate::hash::sha16(&[b"RGB|1x1|", &[0, 0, 0]]));
    }

    #[test]
    fn save_writes_only_ihdr_idat_iend_and_round_trips() {
        let dir = std::env::temp_dir().join(format!("spectre-afk-img-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("x.png");
        let f = Frame::new(3, 2, (0..18).collect());
        save_png(&f, &p).unwrap();
        let bytes = std::fs::read(&p).unwrap();
        let chunks = png_chunks(&bytes);
        assert_eq!(chunks.first().map(String::as_str), Some("IHDR"));
        assert_eq!(chunks.last().map(String::as_str), Some("IEND"));
        assert!(chunks.iter().all(|c| matches!(c.as_str(), "IHDR" | "IDAT" | "IEND")), "{chunks:?}");
        assert_eq!(load_rgb(&p).unwrap(), f);
        std::fs::remove_dir_all(&dir).ok();
    }
}
