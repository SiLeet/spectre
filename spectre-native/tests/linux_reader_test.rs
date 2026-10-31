//! Linux-only integration tests for the `/proc`-based native reader.
//! They inspect the test process itself, which is always readable.
#![cfg(target_os = "linux")]

use spectre_core::types::BackendKind;
use spectre_native::create_default_reader;

#[test]
fn backend_is_native_linux() {
    assert_eq!(
        create_default_reader().backend_kind(),
        BackendKind::NativeLinux
    );
}

#[test]
fn regions_include_rw_region_holding_stack_variable() {
    let reader = create_default_reader();
    let pid = std::process::id();
    let probe = [0x5Au8; 32];
    let addr = std::hint::black_box(&probe) as *const _ as u64;

    let regions = reader.memory_regions(pid).expect("memory_regions");
    assert!(
        regions.iter().any(|r| r.perms.starts_with("rw")),
        "no rw region in {regions:?}"
    );
    let containing = regions
        .iter()
        .find(|r| r.start <= addr && addr < r.end)
        .expect("stack variable must lie inside a listed region");
    assert!(
        containing.perms.starts_with("rw"),
        "stack region not rw: {containing:?}"
    );
}

#[test]
fn read_bytes_reads_own_stack_variable() {
    let reader = create_default_reader();
    let pid = std::process::id();
    let probe: [u8; 16] = *b"SPECTRE_LINUX_OK";
    let addr = std::hint::black_box(&probe) as *const _ as u64;

    let bytes = reader.read_bytes(pid, addr, 16).expect("read_bytes");
    assert_eq!(bytes, probe);

    // Unaligned start and odd length: pread needs no page alignment.
    let bytes = reader
        .read_bytes(pid, addr + 3, 5)
        .expect("unaligned read_bytes");
    assert_eq!(bytes, &probe[3..8]);
}

#[test]
fn read_bytes_unmapped_address_errors() {
    let reader = create_default_reader();
    // Page 0 is never mapped (vm.mmap_min_addr).
    assert!(reader.read_bytes(std::process::id(), 0, 4).is_err());
}

#[test]
fn find_process_finds_self_case_insensitive() {
    let reader = create_default_reader();
    let pid = std::process::id();
    // comm is the binary name truncated to 15 chars, e.g. "linux_reader_te".
    let name = reader
        .process_name(pid)
        .expect("process_name")
        .expect("own comm");
    assert!(name.contains("linux_reader"), "unexpected comm {name:?}");

    let found = reader.find_process("LINUX_READER").expect("find_process");
    assert!(
        found.iter().any(|p| p.pid == pid),
        "own pid {pid} not in {found:?}"
    );
}

#[test]
fn permission_denied_is_reported_clearly() {
    // Only meaningful where the kernel denies us pid 1 (non-root, no ptrace cap).
    let denied = std::fs::File::open("/proc/1/mem")
        .is_err_and(|e| e.kind() == std::io::ErrorKind::PermissionDenied);
    if !denied {
        eprintln!("skipping: /proc/1/mem is readable here (root or same uid)");
        return;
    }
    let err = create_default_reader()
        .read_bytes(1, 0x1000, 4)
        .expect_err("read of pid 1 must fail");
    assert!(
        format!("{err:#}").contains("permission denied (need root or ptrace)"),
        "unexpected error: {err:#}"
    );
}

#[test]
fn read_across_end_of_mapping_errors_instead_of_short_buffer() {
    let reader = create_default_reader();
    let pid = std::process::id();
    let regions = reader.memory_regions(pid).expect("memory_regions");
    // memory_regions drops `---p` guard mappings, which /proc/<pid>/mem can
    // still read (FOLL_FORCE), so look for real gaps in the raw maps.
    let maps = std::fs::read_to_string("/proc/self/maps").expect("maps");
    let starts: Vec<u64> = maps
        .lines()
        .filter_map(|l| u64::from_str_radix(l.split('-').next()?, 16).ok())
        .collect();
    // A readable region followed by unmapped memory whose last bytes are
    // actually readable through /proc/<pid>/mem.
    let r = regions
        .iter()
        .find(|r| {
            r.path.as_deref() != Some("[vsyscall]")
                && !starts.contains(&r.end)
                && reader.read_bytes(pid, r.end - 2, 2).is_ok()
        })
        .expect("a readable region bordering a gap");

    let err = reader
        .read_bytes(pid, r.end - 2, 4)
        .expect_err("read crossing into the gap must fail");
    assert!(
        format!("{err:#}").contains("short read"),
        "unexpected error: {err:#}"
    );
    // Typed reads must surface the error, not panic on a short buffer.
    assert!(reader.read_u32(pid, r.end - 2, true).is_err());
    assert!(reader.read_u64(pid, r.end - 4, true).is_err());
}
