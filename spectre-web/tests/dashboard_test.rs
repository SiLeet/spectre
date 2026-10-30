//! Integration tests for the spectre-web dashboard.
//!
//! Requests go through [`spectre_web::router`] with `tower::ServiceExt::oneshot`
//! (no socket), plus one test that binds port 0 and speaks real HTTP.

use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::Arc;

use axum::body::Body;
use axum::http::{Method, Request, StatusCode, header};
use serde_json::Value;
use spectre_core::reader::MemoryReader;
use spectre_core::scanner::{ScanConfig, scan_memory};
use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use spectre_web::{DashboardApp, router};
use tower::ServiceExt;

const PID: u32 = 1234;
const BASE: u64 = 0x10000;
/// Appears in backend errors; must never reach an HTTP response.
const SECRET_PATH: &str = "C:\\Users\\victim\\secret\\game.exe";

/// Minimal in-memory MemoryReader: one readable region at [`BASE`].
#[derive(Debug)]
struct FakeReader {
    bytes: Vec<u8>,
    processes: Vec<ProcessInfo>,
}

impl FakeReader {
    /// Layout: 0x00 u32 42 · 0x04 f32 3.5 · 0x10 "hello\0" · 0x20.. u32 7 ×5.
    fn new() -> Self {
        let mut bytes = vec![0u8; 0x100];
        bytes[0x00..0x04].copy_from_slice(&42u32.to_le_bytes());
        bytes[0x04..0x08].copy_from_slice(&3.5f32.to_le_bytes());
        bytes[0x10..0x16].copy_from_slice(b"hello\0");
        for i in 0..5 {
            let off = 0x20 + i * 4;
            bytes[off..off + 4].copy_from_slice(&7u32.to_le_bytes());
        }
        Self {
            bytes,
            processes: vec![
                ProcessInfo {
                    pid: PID,
                    name: "fake-game".to_owned(),
                },
                ProcessInfo {
                    pid: 42,
                    name: "other".to_owned(),
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
        let lower = name.to_lowercase();
        Ok(self
            .processes
            .iter()
            .filter(|p| p.name.to_lowercase().contains(&lower))
            .cloned()
            .collect())
    }

    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(self.processes.clone())
    }

    fn memory_regions(&self, pid: u32) -> anyhow::Result<Vec<MemoryRegion>> {
        if pid != PID {
            anyhow::bail!("cannot open {SECRET_PATH} for pid {pid}");
        }
        Ok(vec![MemoryRegion {
            start: BASE,
            end: BASE + self.bytes.len() as u64,
            perms: "rw-p".to_owned(),
            path: Some("fake-game.exe".to_owned()),
        }])
    }

    fn process_name(&self, pid: u32) -> anyhow::Result<Option<String>> {
        Ok(self
            .processes
            .iter()
            .find(|p| p.pid == pid)
            .map(|p| p.name.clone()))
    }

    fn read_bytes(&self, _pid: u32, address: u64, size: u32) -> anyhow::Result<Vec<u8>> {
        let off = address
            .checked_sub(BASE)
            .map(|o| o as usize)
            .filter(|o| *o + size as usize <= self.bytes.len())
            .ok_or_else(|| anyhow::anyhow!("ReadProcessMemory failed reading {SECRET_PATH}"))?;
        Ok(self.bytes[off..off + size as usize].to_vec())
    }

    fn scan(
        &self,
        pid: u32,
        patterns: Vec<ScanPattern>,
        little: bool,
    ) -> anyhow::Result<Vec<ScanReport>> {
        let config = ScanConfig {
            little_endian: little,
            ..Default::default()
        };
        scan_memory(self, pid, patterns, &config)
    }
}

fn app() -> DashboardApp {
    DashboardApp::new(Arc::new(FakeReader::new()))
}

/// Send a request through the router; return status, content type and body.
async fn send(method: Method, uri: &str) -> (StatusCode, String, Vec<u8>) {
    let req = Request::builder()
        .method(method)
        .uri(uri)
        .body(Body::empty())
        .unwrap();
    let res = router(app()).oneshot(req).await.unwrap();
    let status = res.status();
    let ctype = res
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default()
        .to_owned();
    let body = axum::body::to_bytes(res.into_body(), 1 << 20)
        .await
        .unwrap();
    (status, ctype, body.to_vec())
}

/// GET a JSON endpoint and parse the body.
async fn get_json(uri: &str) -> (StatusCode, Value) {
    let (status, ctype, body) = send(Method::GET, uri).await;
    assert!(
        ctype.starts_with("application/json"),
        "{uri}: content-type {ctype}"
    );
    (
        status,
        serde_json::from_slice(&body).expect("valid JSON body"),
    )
}

/// Assert the `{ ok: false, error }` shape and return the error message.
fn expect_error(status: StatusCode, body: &Value, want: StatusCode) -> String {
    assert_eq!(status, want, "body: {body}");
    assert_eq!(body["ok"], false);
    assert!(body.get("data").is_none());
    let msg = body["error"].as_str().expect("error message").to_owned();
    assert!(
        !msg.contains("secret") && !msg.contains('\\'),
        "path leaked: {msg}"
    );
    msg
}

// ── UI ───────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn index_serves_embedded_html() {
    let (status, ctype, body) = send(Method::GET, "/").await;
    assert_eq!(status, StatusCode::OK);
    assert!(ctype.starts_with("text/html"));
    let html = String::from_utf8(body).unwrap();
    assert!(html.contains("<title>Spectre Dashboard</title>"));
    assert!(html.contains("/app.js"));
    assert!(
        !html.contains("http://") && !html.contains("https://"),
        "no external resources"
    );

    let (status, ctype, _) = send(Method::GET, "/app.js").await;
    assert_eq!(status, StatusCode::OK);
    assert!(ctype.starts_with("text/javascript"));
    let (status, ctype, _) = send(Method::GET, "/app.css").await;
    assert_eq!(status, StatusCode::OK);
    assert!(ctype.starts_with("text/css"));
}

#[tokio::test]
async fn unknown_route_and_write_methods_are_rejected() {
    let (status, body) = get_json("/api/nope").await;
    expect_error(status, &body, StatusCode::NOT_FOUND);

    let (status, _, _) = send(Method::POST, "/api/read?pid=1234&addr=0x10000&type=u32").await;
    assert_eq!(status, StatusCode::METHOD_NOT_ALLOWED);
}

// ── /api/info, /api/processes, /api/regions ──────────────────────────────────

#[tokio::test]
async fn info_reports_backend_and_limits() {
    let (status, body) = get_json("/api/info").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["ok"], true);
    assert_eq!(body["data"]["backend"], "DumpFile");
    assert_eq!(body["data"]["max_read_size"], spectre_web::MAX_READ_SIZE);
}

#[tokio::test]
async fn processes_lists_all_sorted_by_pid() {
    let (status, body) = get_json("/api/processes").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["ok"], true);
    let list = body["data"].as_array().unwrap();
    assert_eq!(list.len(), 2);
    assert_eq!(list[0]["pid"], 42);
    assert_eq!(list[1]["pid"], PID);
    assert_eq!(list[1]["name"], "fake-game");
}

#[tokio::test]
async fn processes_name_filter_uses_find_process() {
    let (_, body) = get_json("/api/processes?name=FAKE").await;
    let list = body["data"].as_array().unwrap();
    assert_eq!(list.len(), 1);
    assert_eq!(list[0]["pid"], PID);
}

#[tokio::test]
async fn regions_returns_hex_bounds() {
    let (status, body) = get_json("/api/regions?pid=1234").await;
    assert_eq!(status, StatusCode::OK);
    let r = &body["data"][0];
    assert_eq!(r["start"], "0x10000");
    assert_eq!(r["end"], "0x10100");
    assert_eq!(r["size"], 0x100);
    assert_eq!(r["perms"], "rw-p");

    let (_, body) = get_json("/api/regions?pid=1234&perms=x").await;
    assert_eq!(body["data"].as_array().unwrap().len(), 0);
}

#[tokio::test]
async fn regions_validates_pid_and_hides_backend_errors() {
    let (status, body) = get_json("/api/regions").await;
    let msg = expect_error(status, &body, StatusCode::BAD_REQUEST);
    assert!(msg.contains("pid"));

    let (status, body) = get_json("/api/regions?pid=abc").await;
    expect_error(status, &body, StatusCode::BAD_REQUEST);

    let (status, body) = get_json("/api/regions?pid=99").await;
    expect_error(status, &body, StatusCode::BAD_GATEWAY);
}

// ── /api/read ────────────────────────────────────────────────────────────────

#[tokio::test]
async fn read_u32() {
    let (status, body) = get_json("/api/read?pid=1234&addr=0x10000&type=u32").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["ok"], true);
    let d = &body["data"];
    assert_eq!(d["address"], "0x10000");
    assert_eq!(d["type"], "u32");
    assert_eq!(d["size"], 4);
    assert_eq!(d["value"], 42);
    assert_eq!(d["hex"], "2a 00 00 00");
}

#[tokio::test]
async fn read_u32_big_endian() {
    let (_, body) = get_json("/api/read?pid=1234&addr=0x10000&type=u32&endian=big").await;
    assert_eq!(body["data"]["value"], 0x2a00_0000u32);
}

#[tokio::test]
async fn read_f32() {
    let (status, body) = get_json("/api/read?pid=1234&addr=0x10004&type=f32").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["data"]["value"], 3.5);
}

#[tokio::test]
async fn read_string_stops_at_nul() {
    let (status, body) = get_json("/api/read?pid=1234&addr=0x10010&type=string&size=16").await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["data"]["value"], "hello");
    assert_eq!(body["data"]["size"], 16);
}

#[tokio::test]
async fn read_u64_is_string_for_js_precision() {
    let (_, body) = get_json("/api/read?pid=1234&addr=0x10000&type=u64").await;
    let expected = (42u64 | (u64::from(3.5f32.to_bits()) << 32)).to_string();
    assert_eq!(body["data"]["value"], expected);
}

#[tokio::test]
async fn read_unmapped_address_is_ok_false_without_path() {
    let (status, body) = get_json("/api/read?pid=1234&addr=0xdead0000&type=u32").await;
    let msg = expect_error(status, &body, StatusCode::BAD_GATEWAY);
    assert!(msg.contains("read failed"));
}

#[tokio::test]
async fn read_rejects_bad_params() {
    for uri in [
        "/api/read?pid=1234&addr=0xZZ&type=u32",
        "/api/read?pid=1234&type=u32",
        "/api/read?pid=1234&addr=0x10000&type=u128",
        "/api/read?pid=1234&addr=0x10000&type=u32&endian=middle",
        "/api/read?pid=1234&addr=0xffffffffffffffff&type=u32",
    ] {
        let (status, body) = get_json(uri).await;
        expect_error(status, &body, StatusCode::BAD_REQUEST);
    }
}

#[tokio::test]
async fn read_size_over_cap_is_400() {
    let (status, body) = get_json("/api/read?pid=1234&addr=0x10000&type=bytes&size=4097").await;
    let msg = expect_error(status, &body, StatusCode::BAD_REQUEST);
    assert!(msg.contains("4096"), "{msg}");

    let (status, _) = get_json("/api/read?pid=1234&addr=0x10000&type=bytes&size=4096").await;
    // Allowed by validation; fails only because the fake region is 256 bytes.
    assert_eq!(status, StatusCode::BAD_GATEWAY);
}

// ── /api/search ──────────────────────────────────────────────────────────────

#[tokio::test]
async fn search_finds_value() {
    let (status, body) = get_json("/api/search?pid=1234&type=u32&value=42").await;
    assert_eq!(status, StatusCode::OK);
    let d = &body["data"];
    assert_eq!(d["count"], 1);
    assert_eq!(d["truncated"], false);
    assert_eq!(d["limit"], spectre_web::DEFAULT_SEARCH_LIMIT);
    assert_eq!(d["addresses"][0], "0x10000");
}

#[tokio::test]
async fn search_respects_limit() {
    let (_, body) = get_json("/api/search?pid=1234&type=u32&value=7").await;
    assert_eq!(body["data"]["count"], 5);
    assert_eq!(body["data"]["truncated"], false);

    let (status, body) = get_json("/api/search?pid=1234&type=u32&value=7&limit=2").await;
    assert_eq!(status, StatusCode::OK);
    let d = &body["data"];
    assert_eq!(d["count"], 2);
    assert_eq!(d["truncated"], true);
    assert_eq!(d["addresses"], serde_json::json!(["0x10020", "0x10024"]));
}

#[tokio::test]
async fn search_rejects_bad_params() {
    for uri in [
        "/api/search?pid=1234&type=u32&value=7&limit=0",
        "/api/search?pid=1234&type=u32&value=7&limit=10001",
        "/api/search?pid=1234&type=u32&value=abc",
        "/api/search?pid=1234&type=string&value=x",
        "/api/search?pid=1234&type=u8&value=300",
        "/api/search?type=u32&value=1",
    ] {
        let (status, body) = get_json(uri).await;
        expect_error(status, &body, StatusCode::BAD_REQUEST);
    }
}

// ── Real socket ──────────────────────────────────────────────────────────────

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn serves_real_http_on_port_zero() {
    let server = app().bind(0).await.unwrap();
    let addr = server.local_addr();
    assert!(addr.ip().is_loopback());
    assert_ne!(addr.port(), 0);
    assert_eq!(server.url(), format!("http://127.0.0.1:{}/", addr.port()));

    let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
    let handle = tokio::spawn(server.run_until(async {
        let _ = stop_rx.await;
    }));

    let response = tokio::task::spawn_blocking(move || {
        let mut stream = TcpStream::connect(addr).unwrap();
        stream
            .write_all(
                b"GET /api/processes HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n",
            )
            .unwrap();
        let mut response = String::new();
        stream.read_to_string(&mut response).unwrap();
        response
    })
    .await
    .unwrap();

    assert!(response.starts_with("HTTP/1.1 200"), "{response}");
    let body = response.split("\r\n\r\n").nth(1).unwrap();
    let json: Value = serde_json::from_str(body).unwrap();
    assert_eq!(json["ok"], true);
    assert_eq!(json["data"][1]["name"], "fake-game");

    stop_tx.send(()).unwrap();
    handle.await.unwrap().unwrap();
}
