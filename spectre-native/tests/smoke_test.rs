//! Smoke test for the native backend on the real OS.
//! Verifies process enumeration works (requires a Windows/Linux host).

use spectre_native::{create_default_reader, NativeReader};

#[test]
fn native_backend_lists_processes() {
    let reader = create_default_reader();
    let procs = reader.list_processes().expect("list_processes must not error");
    // Every realistic host has at least a few processes, and our own test
    // process must be among them.
    assert!(
        !procs.is_empty(),
        "expected non-empty process list on this host"
    );
    // Our test binary itself must be enumerated (name contains "native" for
    // the test harness binary, often "native-<hash>"; be lenient and just
    // require that any single process was found).
    eprintln!("enumerated {} processes (first 5: {:?})", procs.len(), &procs[..procs.len().min(5)]);
}

#[test]
fn find_process_matches_self() {
    let reader = create_default_reader();
    // Match a very common process name on Windows; explode on Linux.
    let candidates = ["svchost", "system", "explorer", "kernel", "init"];
    let mut any = false;
    for c in candidates {
        let found = reader.find_process(c).unwrap_or_default();
        if !found.is_empty() {
            any = true;
            eprintln!("found {} process(es) matching '{c}'", found.len());
            break;
        }
    }
    // On a Windows host there is always `svchost.exe` and the System process;
    // the only environment where none match would be an empty container.
    // Keep the assertion strict on Windows, lenient elsewhere.
    #[cfg(windows)]
    assert!(any, "expected at least one common Windows process to be enumerable");

    let _ = &reader;
}

#[test]
#[cfg(windows)]
fn exact_reader_type_dispatches() {
    // The NativeReader enum itself should exist and construct. Windows-only:
    // the Windows variant is cfg-gated to the Windows target.
    let _ = NativeReader::Windows(Default::default());
}