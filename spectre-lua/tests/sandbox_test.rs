//! Integration tests for the Lua sandbox's `spectre` module.
//!
//! Uses an in-memory [`FakeReader`] (same idea as
//! `spectre-core/tests/scanner_test.rs`) so no real process is touched.

use spectre_core::{BackendKind, MemoryReader, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use spectre_lua::{BotApi, LuaSandbox};

const PID: u32 = 1234;
const BASE: u64 = 0x1000;

/// Minimal in-memory MemoryReader: one readable buffer mapped at `BASE`.
#[derive(Debug)]
struct FakeReader {
    bytes: Vec<u8>,
    regions: Vec<MemoryRegion>,
}

impl FakeReader {
    fn new(bytes: Vec<u8>) -> Self {
        let end = BASE + bytes.len() as u64;
        FakeReader {
            bytes,
            regions: vec![
                MemoryRegion {
                    start: BASE,
                    end,
                    perms: "rw-p".to_owned(),
                    path: Some("/data/app/fake-game/lib.so".to_owned()),
                },
                MemoryRegion {
                    start: 0x8000,
                    end: 0x9000,
                    perms: "r-xp".to_owned(),
                    path: None,
                },
            ],
        }
    }
}

impl MemoryReader for FakeReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::DumpFile
    }

    fn find_process(&self, name: &str) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(self
            .list_processes()?
            .into_iter()
            .filter(|p| p.name.contains(&name.to_lowercase()))
            .collect())
    }

    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(vec![ProcessInfo {
            pid: PID,
            name: "fake-game".to_owned(),
        }])
    }

    fn memory_regions(&self, _pid: u32) -> anyhow::Result<Vec<MemoryRegion>> {
        Ok(self.regions.clone())
    }

    fn process_name(&self, _pid: u32) -> anyhow::Result<Option<String>> {
        Ok(Some("fake-game".to_owned()))
    }

    fn read_bytes(&self, _pid: u32, address: u64, size: u32) -> anyhow::Result<Vec<u8>> {
        let start = address
            .checked_sub(BASE)
            .ok_or_else(|| anyhow::anyhow!("address {address:#x} outside fake memory"))?
            as usize;
        let end = start + size as usize;
        if end > self.bytes.len() {
            anyhow::bail!("read {address:#x}+{size} outside fake memory");
        }
        Ok(self.bytes[start..end].to_vec())
    }

    fn scan(
        &self,
        _pid: u32,
        _patterns: Vec<ScanPattern>,
        _little: bool,
    ) -> anyhow::Result<Vec<ScanReport>> {
        Ok(Vec::new())
    }
}

/// BotApi that does nothing.
struct NullBot;

impl BotApi for NullBot {
    fn click(&self, _x: u32, _y: u32) -> anyhow::Result<bool> {
        Ok(true)
    }
    fn swipe(&self, _x1: u32, _y1: u32, _x2: u32, _y2: u32, _ms: u32) -> anyhow::Result<bool> {
        Ok(true)
    }
    fn wait(&self, _ms: u32) -> anyhow::Result<()> {
        Ok(())
    }
    fn log(&self, _message: &str) -> anyhow::Result<()> {
        Ok(())
    }
}

/// Fake memory layout (offsets from `BASE`):
/// - 0x00 u32   = 1337
/// - 0x04 f32   = 2.5
/// - 0x08 u64   = 0x1122_3344_5566_7788
/// - 0x10 i32   = -42
/// - 0x14 u16   = 0xBEEF
/// - 0x16 u8    = 7
/// - 0x18 i64   = -9_000_000_000
/// - 0x20 f64   = 1234.5
/// - 0x28 str   = "Hero\0" (+ padding)
fn sandbox() -> LuaSandbox {
    let mut mem = vec![0u8; 0x40];
    mem[0x00..0x04].copy_from_slice(&1337u32.to_le_bytes());
    mem[0x04..0x08].copy_from_slice(&2.5f32.to_le_bytes());
    mem[0x08..0x10].copy_from_slice(&0x1122_3344_5566_7788u64.to_le_bytes());
    mem[0x10..0x14].copy_from_slice(&(-42i32).to_le_bytes());
    mem[0x14..0x16].copy_from_slice(&0xBEEFu16.to_le_bytes());
    mem[0x16] = 7;
    mem[0x18..0x20].copy_from_slice(&(-9_000_000_000i64).to_le_bytes());
    mem[0x20..0x28].copy_from_slice(&1234.5f64.to_le_bytes());
    mem[0x28..0x2D].copy_from_slice(b"Hero\0");

    LuaSandbox::create(Box::new(FakeReader::new(mem)), Box::new(NullBot)).expect("sandbox creation")
}

#[test]
fn read_u32_returns_value() {
    let sb = sandbox();
    let v: u32 = sb.eval("return spectre.read_u32(1234, 0x1000)").unwrap();
    assert_eq!(v, 1337);
}

#[test]
fn read_fields_mixed_types() {
    let sb = sandbox();
    sb.run(
        r#"
        r = spectre.read_fields(1234, {
            { name = "hp",    addr = 0x1000, type = "u32" },
            { name = "speed", addr = 0x1004, type = "f32" },
            { name = "guid",  addr = 0x1008, type = "u64" },
            { name = "delta", addr = 0x1010, type = "i32" },
            { name = "flags", addr = 0x1014, type = "u16" },
            { name = "lvl",   addr = 0x1016, type = "u8" },
            { name = "gold",  addr = 0x1018, type = "i64" },
            { name = "pos",   addr = 0x1020, type = "F64" },
            { name = "nick",  addr = 0x1028, type = "string", len = 16 },
            { name = "dflt",  addr = 0x1000 },
        })
        "#,
    )
    .unwrap();

    assert_eq!(sb.eval::<u32>("return r.hp").unwrap(), 1337);
    assert_eq!(sb.eval::<f32>("return r.speed").unwrap(), 2.5);
    assert_eq!(
        sb.eval::<u64>("return r.guid").unwrap(),
        0x1122_3344_5566_7788
    );
    assert_eq!(sb.eval::<i32>("return r.delta").unwrap(), -42);
    assert_eq!(sb.eval::<u16>("return r.flags").unwrap(), 0xBEEF);
    assert_eq!(sb.eval::<u8>("return r.lvl").unwrap(), 7);
    assert_eq!(sb.eval::<i64>("return r.gold").unwrap(), -9_000_000_000);
    assert_eq!(sb.eval::<f64>("return r.pos").unwrap(), 1234.5);
    assert_eq!(sb.eval::<String>("return r.nick").unwrap(), "Hero");
    // `type` defaults to u32
    assert_eq!(sb.eval::<u32>("return r.dflt").unwrap(), 1337);
    // integer types come back as Lua integers, floats as floats
    assert_eq!(
        sb.eval::<String>("return math.type(r.hp) .. ',' .. math.type(r.speed)")
            .unwrap(),
        "integer,float"
    );
}

#[test]
fn read_fields_failed_read_leaves_key_absent() {
    let sb = sandbox();
    sb.run(
        r#"
        r = spectre.read_fields(1234, {
            { name = "hp",   addr = 0x1000, type = "u32" },
            { name = "bad",  addr = 0xDEAD0000, type = "u32" },
            { name = "edge", addr = 0x103E, type = "u32" },  -- straddles end of buffer
            { name = "lvl",  addr = 0x1016, type = "u8" },
        })
        n = 0
        for _ in pairs(r) do n = n + 1 end
        "#,
    )
    .unwrap();

    assert_eq!(sb.eval::<u32>("return r.hp").unwrap(), 1337);
    assert_eq!(sb.eval::<u8>("return r.lvl").unwrap(), 7);
    assert!(sb.eval::<bool>("return r.bad == nil").unwrap());
    assert!(sb.eval::<bool>("return r.edge == nil").unwrap());
    assert_eq!(sb.eval::<u32>("return n").unwrap(), 2);
}

#[test]
fn read_fields_unknown_type_is_error() {
    let sb = sandbox();
    let err = sb
        .run(r#"spectre.read_fields(1234, { { name = "x", addr = 0x1000, type = "u128" } })"#)
        .unwrap_err();
    let msg = format!("{err:#}");
    assert!(
        msg.contains("unknown type: u128"),
        "unexpected error: {msg}"
    );
}

#[test]
fn read_fields_string_requires_len() {
    let sb = sandbox();
    let err = sb
        .run(r#"spectre.read_fields(1234, { { name = "nick", addr = 0x1028, type = "string" } })"#)
        .unwrap_err();
    let msg = format!("{err:#}");
    assert!(msg.contains("no `len`"), "unexpected error: {msg}");
}

#[test]
fn read_fields_missing_name_or_addr_is_error() {
    let sb = sandbox();
    assert!(
        sb.run(r#"spectre.read_fields(1234, { { addr = 0x1000 } })"#)
            .is_err()
    );
    assert!(
        sb.run(r#"spectre.read_fields(1234, { { name = "hp" } })"#)
            .is_err()
    );
}

#[test]
fn regions_lists_memory_map() {
    let sb = sandbox();
    sb.run("rs = spectre.regions(1234)").unwrap();

    assert_eq!(sb.eval::<u32>("return #rs").unwrap(), 2);
    assert_eq!(sb.eval::<u64>("return rs[1].start").unwrap(), 0x1000);
    assert_eq!(sb.eval::<u64>("return rs[1].end_addr").unwrap(), 0x1040);
    assert_eq!(sb.eval::<u64>(r#"return rs[1]["end"]"#).unwrap(), 0x1040);
    assert_eq!(sb.eval::<u64>("return rs[1].size").unwrap(), 0x40);
    assert_eq!(sb.eval::<String>("return rs[1].perms").unwrap(), "rw-p");
    assert_eq!(
        sb.eval::<String>("return rs[1].path").unwrap(),
        "/data/app/fake-game/lib.so"
    );

    assert_eq!(sb.eval::<u64>("return rs[2].start").unwrap(), 0x8000);
    assert_eq!(sb.eval::<u64>("return rs[2].size").unwrap(), 0x1000);
    assert_eq!(sb.eval::<String>("return rs[2].perms").unwrap(), "r-xp");
    assert!(sb.eval::<bool>("return rs[2].path == nil").unwrap());
}

#[test]
fn readme_examples_run() {
    let sb = sandbox();
    sb.run(
        r#"
        local pid, base = 1234, 0x1000
        local s = spectre.read_fields(pid, {
            { name = "hp",    addr = base + 0x00, type = "u32" },
            { name = "speed", addr = base + 0x04, type = "f32" },
            { name = "nick",  addr = base + 0x28, type = "string", len = 16 },
        })
        if s.hp then
            bot.log(("%s: %d HP, speed %.2f"):format(s.nick or "?", s.hp, s.speed or 0))
        end
        for i, r in ipairs(spectre.regions(pid)) do
            bot.log(("%#x-%#x %s %d bytes %s"):format(r.start, r.end_addr, r.perms, r.size, r.path or ""))
        end
        "#,
    )
    .unwrap();
}
