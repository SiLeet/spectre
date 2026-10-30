//! Integration tests for the spectre-web dashboard.
//!
//! Requests go through [`spectre_web::router`] with `tower::ServiceExt::oneshot`
//! (no socket), plus one test that binds port 0 and speaks real HTTP.

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use axum::body::Body;
use axum::extract::ConnectInfo;
use axum::http::{HeaderMap, Method, Request, StatusCode, header};
use serde_json::Value;
use spectre_core::reader::MemoryReader;
use spectre_core::scanner::{ScanConfig, scan_memory};
use spectre_core::types::{BackendKind, MemoryRegion, ProcessInfo, ScanPattern, ScanReport};
use spectre_web::{DashboardApp, ManualClock, RateLimit, router};
use tower::ServiceExt;

const PID: u32 = 1234;
const BASE: u64 = 0x10000;
/// Appears in backend errors; must never reach an HTTP response.
const SECRET_PATH: &str = "C:\\Users\\victim\\secret\\game.exe";
/// An environment variable name and value that appear in backend errors.
const SECRET_ENV: &str = "SPECTRE_TEST_TOKEN";
const SECRET_ENV_VALUE: &str = "hunter2-token-value";
/// Reading this address makes [`FakeReader`] panic.
const PANIC_ADDR: u64 = 0xbad0_0000;

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
        if name == "boom" {
            anyhow::bail!("adb failed: {SECRET_ENV}={SECRET_ENV_VALUE} in {SECRET_PATH}");
        }
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
        if address == PANIC_ADDR {
            panic!("reader crashed on {SECRET_PATH} ({SECRET_ENV}={SECRET_ENV_VALUE})");
        }
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
    send_to(router(app()), method, uri, &[]).await
}

/// Send a request with extra headers through `router`.
async fn send_to(
    router: axum::Router,
    method: Method,
    uri: &str,
    headers: &[(&str, &str)],
) -> (StatusCode, String, Vec<u8>) {
    let mut req = Request::builder().method(method).uri(uri);
    for (name, value) in headers {
        req = req.header(*name, *value);
    }
    let req = req.body(Body::empty()).unwrap();
    let res = router.oneshot(req).await.unwrap();
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
    parse_json(uri, status, &ctype, &body)
}

/// Assert a JSON content type and parse `body`.
fn parse_json(uri: &str, status: StatusCode, ctype: &str, body: &[u8]) -> (StatusCode, Value) {
    assert!(
        ctype.starts_with("application/json"),
        "{uri}: content-type {ctype}"
    );
    (
        status,
        serde_json::from_slice(body).expect("valid JSON body"),
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
    assert!(
        !msg.contains(SECRET_ENV) && !msg.contains(SECRET_ENV_VALUE),
        "environment leaked: {msg}"
    );
    msg
}

/// Send a prepared request through `router`; return status, headers, body.
async fn request(router: axum::Router, req: Request<Body>) -> (StatusCode, HeaderMap, Vec<u8>) {
    let res = router.oneshot(req).await.unwrap();
    let status = res.status();
    let headers = res.headers().clone();
    let body = axum::body::to_bytes(res.into_body(), 1 << 20)
        .await
        .unwrap();
    (status, headers, body.to_vec())
}

/// Build a request with the given method, URI and headers.
fn build(method: Method, uri: &str, headers: &[(&str, &str)]) -> Request<Body> {
    let mut req = Request::builder().method(method).uri(uri);
    for (name, value) in headers {
        req = req.header(*name, *value);
    }
    req.body(Body::empty()).unwrap()
}

/// Header value as `&str` (empty if missing).
fn hval(headers: &HeaderMap, name: impl axum::http::header::AsHeaderName) -> &str {
    headers
        .get(name)
        .and_then(|v| v.to_str().ok())
        .unwrap_or_default()
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

    for (method, uri) in [
        (Method::POST, "/api/read?pid=1234&addr=0x10000&type=u32"),
        (Method::DELETE, "/api/search?pid=1234&type=u32&value=7"),
        (Method::PUT, "/api/info"),
    ] {
        let router = router(app());
        let req = Request::builder()
            .method(method)
            .uri(uri)
            .body(Body::empty())
            .unwrap();
        let res = router.oneshot(req).await.unwrap();
        let allow = res.headers().get(header::ALLOW).cloned();
        let ctype = res
            .headers()
            .get(header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .unwrap_or_default()
            .to_owned();
        let status = res.status();
        let body = axum::body::to_bytes(res.into_body(), 1 << 20)
            .await
            .unwrap();
        let (status, body) = parse_json(uri, status, &ctype, &body);
        let msg = expect_error(status, &body, StatusCode::METHOD_NOT_ALLOWED);
        assert!(msg.contains("GET"), "{msg}");
        assert!(allow.is_some_and(|a| a.to_str().unwrap().contains("GET")));
    }
}

// ── Same-origin guard ────────────────────────────────────────────────────────

#[tokio::test]
async fn foreign_host_is_rejected_dns_rebinding() {
    for host in [
        "evil.example",
        "attacker.example:8787",
        "rebind.attacker.example",
        "[::1]:8787",
    ] {
        for uri in [
            "/api/processes",
            "/api/read?pid=1234&addr=0x10000&type=u32",
            "/",
        ] {
            let (status, ctype, body) =
                send_to(router(app()), Method::GET, uri, &[("host", host)]).await;
            let (status, body) = parse_json(uri, status, &ctype, &body);
            expect_error(status, &body, StatusCode::FORBIDDEN);
        }
    }

    for host in ["127.0.0.1:8787", "localhost:8787"] {
        let (status, _, _) = send_to(
            router(app()),
            Method::GET,
            "/api/processes",
            &[("host", host)],
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{host}");
    }
}

#[tokio::test]
async fn cross_origin_and_cross_site_requests_are_rejected() {
    let host = ("host", "127.0.0.1:8787");
    for extra in [
        ("origin", "https://evil.example"),
        ("origin", "null"),
        ("sec-fetch-site", "cross-site"),
        ("sec-fetch-site", "same-site"),
    ] {
        let uri = "/api/search?pid=1234&type=u32&value=7";
        let (status, ctype, body) = send_to(router(app()), Method::GET, uri, &[host, extra]).await;
        let (status, body) = parse_json(uri, status, &ctype, &body);
        expect_error(status, &body, StatusCode::FORBIDDEN);
    }

    // What the dashboard's own fetch() calls look like.
    let (status, _, _) = send_to(
        router(app()),
        Method::GET,
        "/api/search?pid=1234&type=u32&value=7",
        &[
            host,
            ("origin", "http://127.0.0.1:8787"),
            ("sec-fetch-site", "same-origin"),
        ],
    )
    .await;
    assert_eq!(status, StatusCode::OK);
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
    assert_eq!(msg, "read failed");
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

// ── Search budget and cancellation ───────────────────────────────────────────

/// Reader with `regions` small rw regions; every read sleeps `delay` and is
/// counted, so tests can observe whether a scan is still running.
#[derive(Debug)]
struct SlowReader {
    delay: Duration,
    regions: u64,
    reads: Arc<AtomicUsize>,
}

impl MemoryReader for SlowReader {
    fn backend_kind(&self) -> BackendKind {
        BackendKind::DumpFile
    }

    fn find_process(&self, _name: &str) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(Vec::new())
    }

    fn list_processes(&self) -> anyhow::Result<Vec<ProcessInfo>> {
        Ok(Vec::new())
    }

    fn memory_regions(&self, _pid: u32) -> anyhow::Result<Vec<MemoryRegion>> {
        Ok((0..self.regions)
            .map(|i| MemoryRegion {
                start: BASE + i * 0x1000,
                end: BASE + (i + 1) * 0x1000,
                perms: "rw-p".to_owned(),
                path: None,
            })
            .collect())
    }

    fn process_name(&self, _pid: u32) -> anyhow::Result<Option<String>> {
        Ok(None)
    }

    fn read_bytes(&self, _pid: u32, _address: u64, size: u32) -> anyhow::Result<Vec<u8>> {
        std::thread::sleep(self.delay);
        self.reads.fetch_add(1, Ordering::SeqCst);
        Ok(vec![0; size as usize])
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

fn slow_app(delay: Duration, regions: u64) -> (DashboardApp, Arc<AtomicUsize>) {
    let reads = Arc::new(AtomicUsize::new(0));
    let reader = SlowReader {
        delay,
        regions,
        reads: Arc::clone(&reads),
    };
    (DashboardApp::new(Arc::new(reader)), reads)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn concurrent_searches_are_bounded() {
    let (app, _) = slow_app(Duration::from_millis(400), 1);
    let uri = "/api/search?pid=1&type=u32&value=1";

    let running: Vec<_> = (0..spectre_web::MAX_CONCURRENT_SEARCHES)
        .map(|_| tokio::spawn(send_to(router(app.clone()), Method::GET, uri, &[])))
        .collect();
    tokio::time::sleep(Duration::from_millis(100)).await;

    let (status, ctype, body) = send_to(router(app.clone()), Method::GET, uri, &[]).await;
    let (status, body) = parse_json(uri, status, &ctype, &body);
    let msg = expect_error(status, &body, StatusCode::TOO_MANY_REQUESTS);
    assert!(msg.contains("too many searches"), "{msg}");

    for task in running {
        let (status, _, _) = task.await.unwrap();
        assert_eq!(status, StatusCode::OK);
    }
    // Slots are released once the scans finish.
    let (status, _, _) = send_to(router(app), Method::GET, uri, &[]).await;
    assert_eq!(status, StatusCode::OK);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn search_stops_when_client_disconnects() {
    // 1000 regions × 20 ms ≈ 20 s if the scan were never cancelled.
    let (app, reads) = slow_app(Duration::from_millis(20), 1000);
    let server = app.bind(0).await.unwrap();
    let addr = server.local_addr();
    let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
    let handle = tokio::spawn(server.run_until(async {
        let _ = stop_rx.await;
    }));

    tokio::task::spawn_blocking(move || {
        let mut stream = TcpStream::connect(addr).unwrap();
        stream
            .write_all(
                format!("GET /api/search?pid=1&type=u32&value=1 HTTP/1.1\r\nHost: {addr}\r\n\r\n")
                    .as_bytes(),
            )
            .unwrap();
        std::thread::sleep(Duration::from_millis(200));
        // Client gives up: close the connection without reading a response.
    })
    .await
    .unwrap();

    tokio::time::sleep(Duration::from_millis(300)).await;
    let after_disconnect = reads.load(Ordering::SeqCst);
    assert!(after_disconnect > 0, "scan never started");
    tokio::time::sleep(Duration::from_millis(500)).await;
    let later = reads.load(Ordering::SeqCst);
    assert_eq!(
        later, after_disconnect,
        "scan kept reading after the client disconnected"
    );

    stop_tx.send(()).unwrap();
    handle.await.unwrap().unwrap();
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
                format!("GET /api/processes HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n")
                    .as_bytes(),
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

// ── Read-only surface ────────────────────────────────────────────────────────

/// Every route the dashboard serves.
const ROUTES: [&str; 9] = [
    "/",
    "/app.js",
    "/app.css",
    "/favicon.ico",
    "/api/info",
    "/api/processes",
    "/api/regions",
    "/api/read",
    "/api/search",
];

#[tokio::test]
async fn api_has_no_write_or_execute_endpoints() {
    for uri in ROUTES {
        for method in [Method::POST, Method::PUT, Method::PATCH, Method::DELETE] {
            let (status, headers, _) =
                request(router(app()), build(method.clone(), uri, &[])).await;
            assert_eq!(status, StatusCode::METHOD_NOT_ALLOWED, "{method} {uri}");
            assert!(!hval(&headers, header::ALLOW).contains("POST"), "{uri}");
        }
    }
    for uri in [
        "/api/write?pid=1234&addr=0x10000&value=1",
        "/api/exec",
        "/api/bot/start",
        "/api/memory",
    ] {
        for method in [Method::GET, Method::POST] {
            let (status, _, _) = request(router(app()), build(method.clone(), uri, &[])).await;
            assert_eq!(status, StatusCode::NOT_FOUND, "{method} {uri}");
        }
    }
}

// ── Rate limiting ────────────────────────────────────────────────────────────

/// `app()` limited to `n` memory requests per minute, on a manual clock.
fn limited_app(n: u32) -> (DashboardApp, ManualClock) {
    let clock = ManualClock::new();
    let app = app()
        .with_clock(Arc::new(clock.clone()))
        .with_rate_limit(RateLimit::per_minute(n).unwrap());
    (app, clock)
}

/// A GET for `uri` as if it arrived over TCP from `ip`.
fn from_ip(uri: &str, ip: [u8; 4]) -> Request<Body> {
    let mut req = build(Method::GET, uri, &[("host", "127.0.0.1:8787")]);
    req.extensions_mut()
        .insert(ConnectInfo(SocketAddr::from((ip, 50_000))));
    req
}

const READ_URI: &str = "/api/read?pid=1234&addr=0x10000&type=u32";
const SEARCH_URI: &str = "/api/search?pid=1234&type=u32&value=42";
const LOCAL: [u8; 4] = [127, 0, 0, 1];

#[tokio::test]
async fn memory_endpoints_allow_n_then_block_until_window_resets() {
    const N: u32 = 3;
    let (app, clock) = limited_app(N);

    // /api/read and /api/search share one budget per client.
    for (i, uri) in [READ_URI, SEARCH_URI, READ_URI].into_iter().enumerate() {
        let (status, _, _) = request(router(app.clone()), from_ip(uri, LOCAL)).await;
        assert_eq!(status, StatusCode::OK, "request {i}");
    }

    // Request N+1 is refused with the JSON error shape and Retry-After.
    let (status, headers, body) = request(router(app.clone()), from_ip(SEARCH_URI, LOCAL)).await;
    let (status, body) = parse_json(
        SEARCH_URI,
        status,
        hval(&headers, header::CONTENT_TYPE),
        &body,
    );
    let msg = expect_error(status, &body, StatusCode::TOO_MANY_REQUESTS);
    assert!(msg.contains("rate limit exceeded"), "{msg}");
    assert_eq!(hval(&headers, header::RETRY_AFTER), "60");

    // Cheap endpoints are not limited.
    for uri in ["/api/info", "/api/processes", "/api/regions?pid=1234", "/"] {
        let (status, _, _) = request(router(app.clone()), from_ip(uri, LOCAL)).await;
        assert_eq!(status, StatusCode::OK, "{uri}");
    }

    // Another client has its own budget.
    let (status, _, _) = request(router(app.clone()), from_ip(READ_URI, [127, 0, 0, 2])).await;
    assert_eq!(status, StatusCode::OK);

    // Still blocked within the window, with a shrinking Retry-After...
    clock.advance(Duration::from_secs(45));
    let (status, headers, _) = request(router(app.clone()), from_ip(READ_URI, LOCAL)).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);
    assert_eq!(hval(&headers, header::RETRY_AFTER), "15");

    // ...and allowed again once it has elapsed.
    clock.advance(Duration::from_secs(15));
    for _ in 0..N {
        let (status, _, _) = request(router(app.clone()), from_ip(READ_URI, LOCAL)).await;
        assert_eq!(status, StatusCode::OK);
    }
    let (status, _, _) = request(router(app), from_ip(READ_URI, LOCAL)).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);
}

#[tokio::test]
async fn default_rate_limit_is_60_per_minute() {
    let app = app();
    assert_eq!(app.rate_limit(), RateLimit::per_minute(60).unwrap());
    let (_, body) = get_json("/api/info").await;
    assert_eq!(body["data"]["rate_limit_max_requests"], 60);
    assert_eq!(body["data"]["rate_limit_window_secs"], 60);

    for i in 0..60 {
        let (status, _, _) = request(router(app.clone()), from_ip(READ_URI, LOCAL)).await;
        assert_eq!(status, StatusCode::OK, "request {i}");
    }
    let (status, _, _) = request(router(app), from_ip(READ_URI, LOCAL)).await;
    assert_eq!(status, StatusCode::TOO_MANY_REQUESTS);
}

#[tokio::test]
async fn guard_rejections_do_not_use_up_the_budget() {
    let (app, _) = limited_app(1);
    for _ in 0..5 {
        let req = build(Method::GET, READ_URI, &[("host", "evil.example")]);
        let (status, _, _) = request(router(app.clone()), req).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
    }
    let (status, _, _) = request(router(app), from_ip(READ_URI, LOCAL)).await;
    assert_eq!(status, StatusCode::OK);
}

// ── CORS ─────────────────────────────────────────────────────────────────────

const HOST: (&str, &str) = ("host", "127.0.0.1:8787");

#[tokio::test]
async fn cors_is_same_origin_only_by_default() {
    let app = app().with_port(8787);
    assert!(app.allowed_origins().is_empty());

    // The dashboard's own fetch(): allowed, and no CORS headers are needed.
    let req = build(
        Method::GET,
        "/api/info",
        &[
            HOST,
            ("origin", "http://127.0.0.1:8787"),
            ("sec-fetch-site", "same-origin"),
        ],
    );
    let (status, headers, _) = request(router(app.clone()), req).await;
    assert_eq!(status, StatusCode::OK);
    assert!(headers.get(header::ACCESS_CONTROL_ALLOW_ORIGIN).is_none());

    // Other origins, including other local ports, are refused without CORS headers.
    for origin in ["https://tool.example", "http://localhost:3000", "null"] {
        let req = build(Method::GET, "/api/info", &[HOST, ("origin", origin)]);
        let (status, headers, _) = request(router(app.clone()), req).await;
        assert_eq!(status, StatusCode::FORBIDDEN, "{origin}");
        assert!(headers.get(header::ACCESS_CONTROL_ALLOW_ORIGIN).is_none());

        let preflight = build(
            Method::OPTIONS,
            "/api/info",
            &[
                HOST,
                ("origin", origin),
                ("access-control-request-method", "GET"),
            ],
        );
        let (status, headers, _) = request(router(app.clone()), preflight).await;
        assert_eq!(status, StatusCode::FORBIDDEN, "preflight {origin}");
        assert!(headers.get(header::ACCESS_CONTROL_ALLOW_ORIGIN).is_none());
    }
}

#[tokio::test]
async fn cors_allow_list_echoes_only_listed_origins() {
    let app = app()
        .with_port(8787)
        .with_allowed_origins(["https://tool.example"])
        .unwrap();

    let req = build(
        Method::GET,
        "/api/info",
        &[
            HOST,
            ("origin", "https://tool.example"),
            ("sec-fetch-site", "cross-site"),
        ],
    );
    let (status, headers, _) = request(router(app.clone()), req).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        hval(&headers, header::ACCESS_CONTROL_ALLOW_ORIGIN),
        "https://tool.example"
    );
    assert!(hval(&headers, header::ACCESS_CONTROL_ALLOW_METHODS).contains("GET"));
    assert!(hval(&headers, header::VARY).contains("Origin"));
    assert!(
        headers
            .get(header::ACCESS_CONTROL_ALLOW_CREDENTIALS)
            .is_none()
    );

    // Preflight (with Private Network Access) for GET is answered...
    let preflight = |method| {
        build(
            Method::OPTIONS,
            "/api/read",
            &[
                HOST,
                ("origin", "https://tool.example"),
                ("access-control-request-method", method),
                ("access-control-request-private-network", "true"),
            ],
        )
    };
    let (status, headers, _) = request(router(app.clone()), preflight("GET")).await;
    assert_eq!(status, StatusCode::NO_CONTENT);
    assert_eq!(
        hval(&headers, header::ACCESS_CONTROL_ALLOW_ORIGIN),
        "https://tool.example"
    );
    assert_eq!(
        hval(&headers, header::ACCESS_CONTROL_ALLOW_METHODS),
        "GET, HEAD"
    );
    assert_eq!(
        hval(&headers, "access-control-allow-private-network"),
        "true"
    );
    // ...but write methods are not.
    let (status, headers, _) = request(router(app.clone()), preflight("POST")).await;
    assert_eq!(status, StatusCode::METHOD_NOT_ALLOWED);
    assert!(headers.get(header::ACCESS_CONTROL_ALLOW_ORIGIN).is_none());

    // Unlisted origins still get 403 and no CORS headers.
    let req = build(
        Method::GET,
        "/api/info",
        &[HOST, ("origin", "https://evil.example")],
    );
    let (status, headers, _) = request(router(app.clone()), req).await;
    assert_eq!(status, StatusCode::FORBIDDEN);
    assert!(headers.get(header::ACCESS_CONTROL_ALLOW_ORIGIN).is_none());

    // Same-origin requests carry no Access-Control-Allow-Origin, only Vary.
    let req = build(
        Method::GET,
        "/api/info",
        &[HOST, ("origin", "http://localhost:8787")],
    );
    let (status, headers, _) = request(router(app), req).await;
    assert_eq!(status, StatusCode::OK);
    assert!(headers.get(header::ACCESS_CONTROL_ALLOW_ORIGIN).is_none());
    assert!(hval(&headers, header::VARY).contains("Origin"));
}

#[test]
fn cors_allow_list_never_accepts_wildcards() {
    for bad in [
        "*",
        "null",
        "https://*.example.com",
        "https://tool.example/api",
    ] {
        assert!(app().with_allowed_origins([bad]).is_err(), "{bad}");
    }
}

// ── Security headers and Host pinning ────────────────────────────────────────

#[tokio::test]
async fn security_headers_on_html_and_api_responses() {
    let (status, headers, body) = request(router(app()), build(Method::GET, "/", &[])).await;
    assert_eq!(status, StatusCode::OK);
    let csp = hval(&headers, header::CONTENT_SECURITY_POLICY);
    for directive in [
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
    ] {
        assert!(csp.contains(directive), "{csp}");
    }
    assert!(
        !csp.contains("unsafe-inline") && !csp.contains('*'),
        "{csp}"
    );
    // The embedded page must work under that policy: no inline code or styles.
    let html = String::from_utf8(body).unwrap();
    assert!(!html.contains("<script>") && !html.contains("<style"));
    assert!(!html.contains(" style=") && !html.contains(" onclick="));

    for req in [
        build(Method::GET, "/", &[]),
        build(Method::GET, "/app.js", &[]),
        build(Method::GET, "/api/info", &[]),
        build(Method::GET, "/api/nope", &[]),
        build(Method::POST, "/api/read", &[]),
        build(Method::GET, "/api/info", &[("host", "evil.example")]),
    ] {
        let uri = req.uri().to_string();
        let (_, headers, _) = request(router(app()), req).await;
        assert_eq!(
            hval(&headers, header::X_CONTENT_TYPE_OPTIONS),
            "nosniff",
            "{uri}"
        );
        assert_eq!(
            hval(&headers, header::REFERRER_POLICY),
            "no-referrer",
            "{uri}"
        );
        assert_eq!(hval(&headers, header::X_FRAME_OPTIONS), "DENY", "{uri}");
        assert_eq!(hval(&headers, header::CACHE_CONTROL), "no-store", "{uri}");
        assert!(
            hval(&headers, header::CONTENT_SECURITY_POLICY).starts_with("default-src 'none'"),
            "{uri}"
        );
    }
    let (_, headers, _) = request(router(app()), build(Method::GET, "/api/info", &[])).await;
    assert!(hval(&headers, header::CONTENT_SECURITY_POLICY).contains("sandbox"));
}

#[tokio::test]
async fn host_must_name_the_dashboard_port() {
    let pinned = || router(app().with_port(8787));
    for host in ["127.0.0.1:8787", "localhost:8787"] {
        let req = build(Method::GET, "/api/info", &[("host", host)]);
        let (status, _, _) = request(pinned(), req).await;
        assert_eq!(status, StatusCode::OK, "{host}");
    }
    for host in [
        "127.0.0.1:8788",
        "localhost:80",
        "localhost",
        "127.0.0.1",
        "[::1]:8787",
        "evil.example:8787",
    ] {
        let req = build(Method::GET, "/api/info", &[("host", host)]);
        let (status, headers, body) = request(pinned(), req).await;
        let (status, body) = parse_json(host, status, hval(&headers, header::CONTENT_TYPE), &body);
        expect_error(status, &body, StatusCode::FORBIDDEN);
    }
}

/// Send raw HTTP to `addr` with the given `Host` and return the status line.
fn raw_status(addr: SocketAddr, host: &str) -> String {
    let mut stream = TcpStream::connect(addr).unwrap();
    let req = format!("GET /api/info HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n");
    stream.write_all(req.as_bytes()).unwrap();
    let mut response = String::new();
    stream.read_to_string(&mut response).unwrap();
    response.lines().next().unwrap_or_default().to_owned()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn bound_server_pins_host_to_its_port() {
    let server = app().bind(0).await.unwrap();
    let addr = server.local_addr();
    let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
    let handle = tokio::spawn(server.run_until(async {
        let _ = stop_rx.await;
    }));

    let port = addr.port();
    let statuses = tokio::task::spawn_blocking(move || {
        [
            format!("127.0.0.1:{port}"),
            format!("localhost:{port}"),
            format!("127.0.0.1:{}", port.wrapping_add(1)),
            format!("rebind.attacker.example:{port}"),
        ]
        .map(|host| raw_status(addr, &host))
    })
    .await
    .unwrap();
    assert!(statuses[0].starts_with("HTTP/1.1 200"), "{statuses:?}");
    assert!(statuses[1].starts_with("HTTP/1.1 200"), "{statuses:?}");
    assert!(statuses[2].starts_with("HTTP/1.1 403"), "{statuses:?}");
    assert!(statuses[3].starts_with("HTTP/1.1 403"), "{statuses:?}");

    stop_tx.send(()).unwrap();
    handle.await.unwrap().unwrap();
}

// ── Error responses ──────────────────────────────────────────────────────────

#[tokio::test]
async fn error_responses_are_generic_without_paths_or_env() {
    let cases = [
        (
            "/api/processes?name=boom",
            StatusCode::BAD_GATEWAY,
            "failed to list processes",
        ),
        (
            "/api/regions?pid=99",
            StatusCode::BAD_GATEWAY,
            "failed to list memory regions",
        ),
        (
            "/api/read?pid=1234&addr=0xdead0000&type=u32",
            StatusCode::BAD_GATEWAY,
            "read failed",
        ),
        (
            "/api/search?pid=99&type=u32&value=1",
            StatusCode::BAD_GATEWAY,
            "search failed",
        ),
        (
            "/api/read?pid=1234&addr=0xbad00000&type=u32",
            StatusCode::INTERNAL_SERVER_ERROR,
            "internal error",
        ),
        (
            "/C:/Users/victim/secret/game.exe",
            StatusCode::NOT_FOUND,
            "not found",
        ),
    ];
    for (uri, want_status, want_msg) in cases {
        let (status, ctype, body) = send(Method::GET, uri).await;
        let raw = String::from_utf8_lossy(&body).into_owned();
        for secret in [SECRET_PATH, "victim", SECRET_ENV, SECRET_ENV_VALUE, "C:\\"] {
            assert!(!raw.contains(secret), "{uri} leaked {secret}: {raw}");
        }
        let (status, body) = parse_json(uri, status, &ctype, &body);
        let msg = expect_error(status, &body, want_status);
        assert_eq!(msg, want_msg, "{uri}");
        // Exactly { ok, error } — no extra detail fields.
        assert_eq!(body.as_object().unwrap().len(), 2, "{uri}: {body}");
    }

    // Validation errors do not echo the offending input either.
    let (status, body) = get_json("/api/read?pid=1234&addr=C:%5CUsers%5Cvictim&type=u32").await;
    let msg = expect_error(status, &body, StatusCode::BAD_REQUEST);
    assert!(!msg.contains("victim"), "{msg}");
}
