//! HTTP routes: embedded UI assets and the read-only JSON API.
//!
//! The router is assembled from three groups so middleware can be layered
//! per group: [`ui_routes`] (static assets), [`meta_routes`] (cheap listing
//! endpoints) and [`memory_routes`] (endpoints that read process memory —
//! the natural place for rate limiting).

use std::sync::Arc;

use axum::extract::rejection::QueryRejection;
use axum::extract::{Query, State};
use axum::http::header;
use axum::response::{Html, IntoResponse};
use axum::routing::get;
use axum::{Json, Router, middleware};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use spectre_core::{
    MemoryReader, PatternField, ScanConfig, ScanPattern, ScanValue, ValueType, scan_memory,
};
use tracing::{debug, error, warn};

use crate::error::{ApiError, ApiOk, ok};
use crate::params::{self, ReadKind};
use crate::{
    DEFAULT_SEARCH_LIMIT, DashboardApp, MAX_CONCURRENT_SEARCHES, MAX_READ_SIZE, MAX_SEARCH_LIMIT,
    cancel, guard,
};

const INDEX_HTML: &str = include_str!("../assets/index.html");
const APP_JS: &str = include_str!("../assets/app.js");
const APP_CSS: &str = include_str!("../assets/app.css");

type ApiResult<T> = Result<Json<ApiOk<T>>, ApiError>;

/// Build the complete dashboard router for `app`.
///
/// Usable without a socket (e.g. `tower::ServiceExt::oneshot` in tests) and
/// as the base for additional middleware layers. Every route, including the
/// 404/405 fallbacks, sits behind the same-origin guard ([`crate::guard`]).
pub fn router(app: DashboardApp) -> Router {
    Router::new()
        .merge(ui_routes())
        .merge(meta_routes())
        .merge(memory_routes())
        .fallback(not_found)
        .method_not_allowed_fallback(method_not_allowed)
        .layer(middleware::from_fn(guard::same_origin_only))
        .with_state(app)
}

/// Embedded, offline UI: HTML, script and stylesheet.
fn ui_routes() -> Router<DashboardApp> {
    Router::new()
        .route("/", get(index))
        .route("/app.js", get(app_js))
        .route("/app.css", get(app_css))
        .route("/favicon.ico", get(favicon))
}

/// Cheap endpoints: backend info, process and region listings.
fn meta_routes() -> Router<DashboardApp> {
    Router::new()
        .route("/api/info", get(api_info))
        .route("/api/processes", get(api_processes))
        .route("/api/regions", get(api_regions))
}

/// Endpoints that read target-process memory (potentially expensive).
fn memory_routes() -> Router<DashboardApp> {
    Router::new()
        .route("/api/read", get(api_read))
        .route("/api/search", get(api_search))
}

// ── Static Assets ────────────────────────────────────────────────────────────

async fn index() -> Html<&'static str> {
    Html(INDEX_HTML)
}

async fn app_js() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/javascript; charset=utf-8")],
        APP_JS,
    )
}

async fn app_css() -> impl IntoResponse {
    ([(header::CONTENT_TYPE, "text/css; charset=utf-8")], APP_CSS)
}

async fn favicon() -> axum::http::StatusCode {
    axum::http::StatusCode::NO_CONTENT
}

async fn not_found() -> ApiError {
    ApiError::not_found()
}

/// JSON 405 for non-`GET` methods (axum still adds the `Allow` header).
async fn method_not_allowed() -> ApiError {
    ApiError::method_not_allowed()
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/// Turn axum's plain-text query rejection into the JSON error shape.
fn query<T>(q: Result<Query<T>, QueryRejection>) -> Result<T, ApiError> {
    q.map(|Query(v)| v).map_err(|e| {
        debug!("query rejected: {e}");
        ApiError::bad_request("malformed query string")
    })
}

/// Run blocking work on tokio's blocking pool.
async fn blocking<T, F>(f: F) -> Result<T, ApiError>
where
    T: Send + 'static,
    F: FnOnce() -> Result<T, ApiError> + Send + 'static,
{
    tokio::task::spawn_blocking(f).await.map_err(|e| {
        error!("reader task failed: {e}");
        ApiError::internal()
    })?
}

/// Run a blocking reader call on tokio's blocking pool.
async fn with_reader<T, F>(app: &DashboardApp, f: F) -> Result<T, ApiError>
where
    T: Send + 'static,
    F: FnOnce(&dyn MemoryReader) -> Result<T, ApiError> + Send + 'static,
{
    let reader = app.reader().clone();
    blocking(move || f(reader.as_ref())).await
}

fn hex_bytes(bytes: &[u8]) -> String {
    bytes
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(" ")
}

// ── /api/info ────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct InfoDto {
    name: &'static str,
    version: &'static str,
    backend: String,
    max_read_size: u32,
    default_search_limit: u32,
    max_search_limit: u32,
}

async fn api_info(State(app): State<DashboardApp>) -> ApiResult<InfoDto> {
    Ok(ok(InfoDto {
        name: env!("CARGO_PKG_NAME"),
        version: env!("CARGO_PKG_VERSION"),
        backend: format!("{:?}", app.reader().backend_kind()),
        max_read_size: MAX_READ_SIZE,
        default_search_limit: DEFAULT_SEARCH_LIMIT,
        max_search_limit: MAX_SEARCH_LIMIT,
    }))
}

// ── /api/processes ───────────────────────────────────────────────────────────

#[derive(Debug, Default, Deserialize)]
struct ProcessesQuery {
    name: Option<String>,
}

#[derive(Debug, Serialize)]
struct ProcessDto {
    pid: u32,
    name: String,
}

async fn api_processes(
    State(app): State<DashboardApp>,
    q: Result<Query<ProcessesQuery>, QueryRejection>,
) -> ApiResult<Vec<ProcessDto>> {
    let q = query(q)?;
    let name = params::parse_filter(q.name.as_deref(), "name")?;
    let mut processes = with_reader(&app, move |reader| {
        let result = match &name {
            Some(n) => reader.find_process(n),
            None => reader.list_processes(),
        };
        result.map_err(|e| {
            warn!("process listing failed: {e:#}");
            ApiError::backend("failed to list processes")
        })
    })
    .await?;
    processes.sort_by_key(|p| p.pid);
    Ok(ok(processes
        .into_iter()
        .map(|p| ProcessDto {
            pid: p.pid,
            name: p.name,
        })
        .collect()))
}

// ── /api/regions ─────────────────────────────────────────────────────────────

#[derive(Debug, Default, Deserialize)]
struct RegionsQuery {
    pid: Option<String>,
    perms: Option<String>,
}

#[derive(Debug, Serialize)]
struct RegionDto {
    start: String,
    end: String,
    size: u64,
    perms: String,
    path: Option<String>,
}

async fn api_regions(
    State(app): State<DashboardApp>,
    q: Result<Query<RegionsQuery>, QueryRejection>,
) -> ApiResult<Vec<RegionDto>> {
    let q = query(q)?;
    let pid = params::parse_pid(q.pid.as_deref())?;
    let perms = params::parse_filter(q.perms.as_deref(), "perms")?.map(|p| p.to_lowercase());
    let regions = with_reader(&app, move |reader| {
        reader.memory_regions(pid).map_err(|e| {
            warn!("memory_regions({pid}) failed: {e:#}");
            ApiError::backend(format!("failed to list memory regions for pid {pid}"))
        })
    })
    .await?;
    Ok(ok(regions
        .into_iter()
        .filter(|r| {
            perms
                .as_ref()
                .is_none_or(|p| r.perms.to_lowercase().contains(p.as_str()))
        })
        .map(|r| RegionDto {
            start: format!("{:#x}", r.start),
            end: format!("{:#x}", r.end),
            size: r.size(),
            perms: r.perms,
            path: r.path,
        })
        .collect()))
}

// ── /api/read ────────────────────────────────────────────────────────────────

#[derive(Debug, Default, Deserialize)]
struct ReadQuery {
    pid: Option<String>,
    addr: Option<String>,
    #[serde(rename = "type")]
    value_type: Option<String>,
    size: Option<String>,
    endian: Option<String>,
}

#[derive(Debug, Serialize)]
struct ReadDto {
    pid: u32,
    address: String,
    #[serde(rename = "type")]
    value_type: &'static str,
    size: u32,
    endian: &'static str,
    /// Decoded value: number, string (64-bit integers and non-finite floats
    /// are strings to survive JavaScript's f64 numbers), or hex for `bytes`.
    value: Value,
    hex: String,
}

async fn api_read(
    State(app): State<DashboardApp>,
    q: Result<Query<ReadQuery>, QueryRejection>,
) -> ApiResult<ReadDto> {
    let q = query(q)?;
    let pid = params::parse_pid(q.pid.as_deref())?;
    let address = params::parse_address(q.addr.as_deref())?;
    let kind = params::parse_read_kind(q.value_type.as_deref())?;
    let requested = params::parse_size(q.size.as_deref())?;
    let little = params::parse_endian(q.endian.as_deref())?;
    let size = match kind {
        ReadKind::Number(vt) => vt.size(),
        ReadKind::String | ReadKind::Bytes => requested,
    };
    if address.checked_add(u64::from(size)).is_none() {
        return Err(ApiError::bad_request(
            "invalid 'addr': address + size overflows",
        ));
    }

    let bytes = with_reader(&app, move |reader| {
        let read_failed = || {
            ApiError::backend(format!(
                "read failed: {size} byte(s) at {address:#x} (pid {pid})"
            ))
        };
        let bytes = reader.read_bytes(pid, address, size).map_err(|e| {
            debug!("read_bytes({pid}, {address:#x}, {size}) failed: {e:#}");
            read_failed()
        })?;
        if bytes.len() < size as usize {
            warn!(
                "backend returned {} of {size} bytes at {address:#x}",
                bytes.len()
            );
            return Err(read_failed());
        }
        Ok(bytes)
    })
    .await?;
    let bytes = &bytes[..size as usize];

    Ok(ok(ReadDto {
        pid,
        address: format!("{address:#x}"),
        value_type: kind.name(),
        size,
        endian: if little { "little" } else { "big" },
        value: decode(kind, bytes, little),
        hex: hex_bytes(bytes),
    }))
}

/// Copy the first `N` bytes into an array in little-endian order.
fn le_array<const N: usize>(bytes: &[u8], little: bool) -> [u8; N] {
    let mut out = [0u8; N];
    out.copy_from_slice(&bytes[..N]);
    if !little {
        out.reverse();
    }
    out
}

fn float_value(v: f64) -> Value {
    serde_json::Number::from_f64(v).map_or_else(|| Value::String(v.to_string()), Value::Number)
}

/// Decode `bytes` (already length-checked) as `kind`.
fn decode(kind: ReadKind, bytes: &[u8], little: bool) -> Value {
    match kind {
        ReadKind::Number(vt) => match vt {
            ValueType::U8 => Value::from(bytes[0]),
            ValueType::I8 => Value::from(bytes[0] as i8),
            ValueType::U16 => Value::from(u16::from_le_bytes(le_array(bytes, little))),
            ValueType::I16 => Value::from(i16::from_le_bytes(le_array(bytes, little))),
            ValueType::U32 => Value::from(u32::from_le_bytes(le_array(bytes, little))),
            ValueType::I32 => Value::from(i32::from_le_bytes(le_array(bytes, little))),
            ValueType::U64 => {
                Value::String(u64::from_le_bytes(le_array(bytes, little)).to_string())
            }
            ValueType::I64 => {
                Value::String(i64::from_le_bytes(le_array(bytes, little)).to_string())
            }
            ValueType::F32 => float_value(f64::from(f32::from_le_bytes(le_array(bytes, little)))),
            ValueType::F64 => float_value(f64::from_le_bytes(le_array(bytes, little))),
            ValueType::Bytes(_) => Value::String(hex_bytes(bytes)),
        },
        ReadKind::String => {
            // Same semantics as MemoryReader::read_string: stop at the first
            // NUL, lossy UTF-8.
            let end = bytes.iter().position(|&b| b == 0).unwrap_or(bytes.len());
            Value::String(String::from_utf8_lossy(&bytes[..end]).into_owned())
        }
        ReadKind::Bytes => Value::String(hex_bytes(bytes)),
    }
}

// ── /api/search ──────────────────────────────────────────────────────────────

#[derive(Debug, Default, Deserialize)]
struct SearchQuery {
    pid: Option<String>,
    #[serde(rename = "type")]
    value_type: Option<String>,
    value: Option<String>,
    limit: Option<String>,
    endian: Option<String>,
}

#[derive(Debug, Serialize)]
struct SearchDto {
    pid: u32,
    #[serde(rename = "type")]
    value_type: &'static str,
    value: String,
    limit: u32,
    count: usize,
    /// `true` when more matches exist than `limit`.
    truncated: bool,
    addresses: Vec<String>,
}

async fn api_search(
    State(app): State<DashboardApp>,
    q: Result<Query<SearchQuery>, QueryRejection>,
) -> ApiResult<SearchDto> {
    let q = query(q)?;
    let pid = params::parse_pid(q.pid.as_deref())?;
    let little = params::parse_endian(q.endian.as_deref())?;
    let sv = params::parse_search_value(q.value_type.as_deref(), q.value.as_deref(), little)?;
    let limit = params::parse_limit(q.limit.as_deref())?;
    let value_type = sv.value_type;

    // Bound concurrent full-memory scans. The permit moves into the blocking
    // task, so it is held until the scan really stops — even after the
    // client has gone away.
    let permit = Arc::clone(app.search_slots())
        .try_acquire_owned()
        .map_err(|_| {
            ApiError::busy(format!(
                "too many searches running (max {MAX_CONCURRENT_SEARCHES}); try again later"
            ))
        })?;
    // Dropping this handler's future (client disconnect) drops `_cancel`,
    // which makes the remaining reads of the scan fail fast.
    let (reader, _cancel) = cancel::cancellable(Arc::clone(app.reader()));

    let mut found = blocking(move || {
        let _permit = permit;
        let align = value_type.size().max(1);
        let pattern = ScanPattern {
            name: "search".to_owned(),
            fields: vec![PatternField {
                name: "value".to_owned(),
                value_type,
                value: ScanValue::Exact(sv.bytes),
                alignment: align,
            }],
        };
        // One extra match tells us whether the result was truncated.
        let config = ScanConfig {
            alignment: align,
            little_endian: little,
            max_matches_per_pattern: limit + 1,
            ..Default::default()
        };
        let reports = scan_memory(&reader, pid, vec![pattern], &config).map_err(|e| {
            warn!("search in pid {pid} failed: {e:#}");
            ApiError::backend(format!("search failed for pid {pid}"))
        })?;
        Ok(reports
            .into_iter()
            .flat_map(|r| r.matches.into_iter().map(|m| m.address))
            .collect::<Vec<u64>>())
    })
    .await?;

    let truncated = found.len() > limit as usize;
    found.truncate(limit as usize);
    Ok(ok(SearchDto {
        pid,
        value_type: params::value_type_name(value_type),
        value: q.value.unwrap_or_default().trim().to_owned(),
        limit,
        count: found.len(),
        truncated,
        addresses: found.iter().map(|a| format!("{a:#x}")).collect(),
    }))
}
