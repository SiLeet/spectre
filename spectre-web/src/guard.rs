//! Origin guard: defence against DNS rebinding and cross-site requests, and
//! the (opt-in) CORS allow-list.
//!
//! Binding to `127.0.0.1` keeps other machines out, but not other *websites*:
//! a page the user visits can rebind its own hostname to `127.0.0.1` and then
//! talk to the dashboard as a same-origin request (CORS does not apply), or
//! fire blind cross-site `GET`s (`<img src>`, `fetch(.., {mode: "no-cors"})`).
//! Every request therefore has to pass three checks:
//!
//! 1. `Host` (or the URI authority) must be `127.0.0.1:PORT` or
//!    `localhost:PORT`, where `PORT` is the port the dashboard is bound to (a
//!    missing port means 80). A rebinding attacker cannot make the browser
//!    send one of these for its own origin. `[::1]` is not accepted: the
//!    server listens on IPv4 only. Requests without any host (raw HTTP/1.0
//!    tools) are allowed; browsers always send `Host`.
//! 2. `Origin`, when present, must be the dashboard's own origin
//!    (`http://127.0.0.1:PORT` or `http://localhost:PORT`) or one of the
//!    configured allowed origins. `null` and wildcards are never accepted.
//! 3. For `/api/*` requests that are not from an allowed origin,
//!    `Sec-Fetch-Site`, when present, must be `same-origin` or `none` (typed
//!    into the address bar). This stops cross-site `GET`s that carry no
//!    `Origin` header. UI routes skip this check so that following a link to
//!    the dashboard from another page still works.
//!
//! # CORS
//!
//! By default (empty allow-list) the API is same-origin only and no
//! `Access-Control-*` header is ever sent. Origins added with
//! [`crate::DashboardApp::with_allowed_origins`] get their own origin echoed
//! in `Access-Control-Allow-Origin` (never `*`), with `Vary: Origin`, and
//! their preflights (including Private Network Access) are answered for
//! `GET`/`HEAD` only.
//!
//! When the guard does not know the port (a router built directly from
//! [`crate::router`] without [`crate::DashboardApp::with_port`] or
//! [`crate::DashboardApp::bind`]), the port part of checks 1 and 2 is
//! skipped.

use std::sync::Arc;

use anyhow::{Result, bail};
use axum::extract::{Request, State};
use axum::http::uri::Authority;
use axum::http::{HeaderMap, HeaderName, HeaderValue, Method, StatusCode, Uri, header};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use tracing::warn;

use crate::error::ApiError;

/// `Sec-Fetch-Site` request header (Fetch Metadata).
const SEC_FETCH_SITE: HeaderName = HeaderName::from_static("sec-fetch-site");
/// Private Network Access preflight request header.
const ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK: HeaderName =
    HeaderName::from_static("access-control-request-private-network");
/// Private Network Access preflight response header.
const ACCESS_CONTROL_ALLOW_PRIVATE_NETWORK: HeaderName =
    HeaderName::from_static("access-control-allow-private-network");

/// Hostnames under which the dashboard may legitimately be addressed.
const LOOPBACK_HOSTS: [&str; 2] = ["127.0.0.1", "localhost"];

/// How long browsers may cache a successful preflight, in seconds.
const PREFLIGHT_MAX_AGE: &str = "600";

/// Configuration of the origin guard, shared by all requests.
#[derive(Debug, Clone, Default)]
pub(crate) struct Guard {
    /// Port the dashboard listens on; `None` skips the port checks.
    port: Option<u16>,
    /// Normalised (see [`normalize_origin`]) extra origins allowed via CORS.
    allowed_origins: Arc<[String]>,
}

/// How a request that passed the guard relates to the dashboard.
#[derive(Debug, Clone, PartialEq, Eq)]
enum Access {
    /// Same-origin, or not from a browser page at all.
    SameOrigin,
    /// Cross-origin from an allow-listed origin; holds the `Origin` value.
    Cors(HeaderValue),
}

impl Guard {
    /// Pin the port that `Host` and same-origin `Origin` headers must name.
    pub(crate) fn with_port(mut self, port: u16) -> Self {
        self.port = Some(port);
        self
    }

    /// Replace the CORS allow-list. Every entry must be an `http://` or
    /// `https://` origin (`scheme://host[:port]`, no path, no wildcard).
    pub(crate) fn with_allowed_origins<I, S>(mut self, origins: I) -> Result<Self>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        let mut list = Vec::new();
        for origin in origins {
            let origin = origin.as_ref().trim();
            if origin == "*" || origin.contains('*') {
                bail!("invalid allowed origin {origin:?}: wildcards are not allowed");
            }
            let Some(normalized) = normalize_origin(origin) else {
                bail!(
                    "invalid allowed origin {origin:?}: expected scheme://host[:port] \
                     with scheme http or https and no path"
                );
            };
            if !list.contains(&normalized) {
                list.push(normalized);
            }
        }
        self.allowed_origins = list.into();
        Ok(self)
    }

    /// The configured CORS allow-list (normalised).
    pub(crate) fn allowed_origins(&self) -> &[String] {
        &self.allowed_origins
    }

    /// Validate `Host`, `Origin` and (for API paths) `Sec-Fetch-Site`.
    fn check(&self, headers: &HeaderMap, uri: &Uri) -> Result<Access, ApiError> {
        let host = match headers.get(header::HOST) {
            Some(v) => Some(
                v.to_str()
                    .ok()
                    .and_then(|s| s.parse::<Authority>().ok())
                    .ok_or_else(|| ApiError::forbidden("forbidden: malformed Host header"))?,
            ),
            None => uri.authority().cloned(),
        };
        if let Some(host) = host
            && !self.is_dashboard_authority(&host)
        {
            return Err(ApiError::forbidden(
                "forbidden: unexpected Host header (open the dashboard via http://127.0.0.1:<port>/)",
            ));
        }

        let access = match headers.get(header::ORIGIN) {
            None => Access::SameOrigin,
            Some(origin) => self.classify_origin(origin)?,
        };

        if access == Access::SameOrigin
            && uri.path().starts_with("/api/")
            && let Some(site) = headers.get(SEC_FETCH_SITE)
            && !matches!(site.as_bytes(), b"same-origin" | b"none")
        {
            return Err(ApiError::forbidden("forbidden: cross-site request"));
        }
        Ok(access)
    }

    /// Same origin, allow-listed origin, or 403.
    fn classify_origin(&self, origin: &HeaderValue) -> Result<Access, ApiError> {
        let raw = origin.to_str().ok();
        let same_origin = raw.and_then(|s| s.parse::<Uri>().ok()).is_some_and(|o| {
            o.scheme_str() == Some("http")
                && o.authority()
                    .is_some_and(|a| self.is_dashboard_authority(a))
        });
        if same_origin {
            return Ok(Access::SameOrigin);
        }
        let allowed = raw
            .and_then(normalize_origin)
            .is_some_and(|o| self.allowed_origins.contains(&o));
        if allowed {
            return Ok(Access::Cors(origin.clone()));
        }
        Err(ApiError::forbidden("forbidden: cross-origin request"))
    }

    /// Is `authority` one of our loopback names, on our port if known?
    fn is_dashboard_authority(&self, authority: &Authority) -> bool {
        let host_ok = LOOPBACK_HOSTS
            .iter()
            .any(|h| authority.host().eq_ignore_ascii_case(h));
        let port_ok = self
            .port
            .is_none_or(|p| authority.port_u16().unwrap_or(80) == p);
        host_ok && port_ok && !authority.as_str().contains('@')
    }
}

/// Middleware: reject requests that do not originate from the dashboard
/// itself or an allowed origin (see the module docs) with a JSON 403, answer
/// CORS preflights and add CORS headers for allowed origins.
pub(crate) async fn origin_guard(State(guard): State<Guard>, req: Request, next: Next) -> Response {
    let access = match guard.check(req.headers(), req.uri()) {
        Ok(access) => access,
        Err(e) => {
            warn!(
                "rejected {} {}: {}",
                req.method(),
                req.uri().path(),
                e.message()
            );
            return e.into_response();
        }
    };
    let cors_enabled = !guard.allowed_origins().is_empty();

    let mut res = match access {
        Access::SameOrigin => next.run(req).await,
        Access::Cors(origin) => {
            if req.method() == Method::OPTIONS
                && req
                    .headers()
                    .contains_key(header::ACCESS_CONTROL_REQUEST_METHOD)
            {
                preflight(req.headers(), origin)
            } else {
                let mut res = next.run(req).await;
                let headers = res.headers_mut();
                headers.insert(header::ACCESS_CONTROL_ALLOW_ORIGIN, origin);
                headers.insert(
                    header::ACCESS_CONTROL_ALLOW_METHODS,
                    HeaderValue::from_static("GET, HEAD"),
                );
                res
            }
        }
    };
    if cors_enabled {
        // Responses differ per Origin once an allow-list exists.
        res.headers_mut()
            .append(header::VARY, HeaderValue::from_static("Origin"));
    }
    res
}

/// Answer a CORS preflight from an allow-listed `origin`: only `GET`/`HEAD`
/// may follow, the API being read-only.
fn preflight(headers: &HeaderMap, origin: HeaderValue) -> Response {
    let method = headers
        .get(header::ACCESS_CONTROL_REQUEST_METHOD)
        .map(HeaderValue::as_bytes);
    if !matches!(method, Some(b"GET" | b"HEAD")) {
        warn!("rejected CORS preflight for a non-GET method");
        return ApiError::method_not_allowed().into_response();
    }
    let mut res = StatusCode::NO_CONTENT.into_response();
    let out = res.headers_mut();
    out.insert(header::ACCESS_CONTROL_ALLOW_ORIGIN, origin);
    out.insert(
        header::ACCESS_CONTROL_ALLOW_METHODS,
        HeaderValue::from_static("GET, HEAD"),
    );
    out.insert(
        header::ACCESS_CONTROL_MAX_AGE,
        HeaderValue::from_static(PREFLIGHT_MAX_AGE),
    );
    if headers
        .get(ACCESS_CONTROL_REQUEST_PRIVATE_NETWORK)
        .is_some_and(|v| v.as_bytes().eq_ignore_ascii_case(b"true"))
    {
        out.insert(
            ACCESS_CONTROL_ALLOW_PRIVATE_NETWORK,
            HeaderValue::from_static("true"),
        );
    }
    res
}

/// Canonical form of a web origin: lowercase `scheme://host[:port]`, default
/// ports (80/443) dropped. `None` for anything that is not an `http(s)`
/// origin (paths, queries, credentials, `null`, other schemes).
fn normalize_origin(raw: &str) -> Option<String> {
    let raw = raw.strip_suffix('/').unwrap_or(raw);
    let uri = raw.parse::<Uri>().ok()?;
    let scheme = uri.scheme_str()?.to_ascii_lowercase();
    let default_port = match scheme.as_str() {
        "http" => 80,
        "https" => 443,
        _ => return None,
    };
    let authority = uri.authority()?;
    if authority.as_str().contains('@') || authority.host().is_empty() {
        return None;
    }
    if uri
        .path_and_query()
        .is_some_and(|pq| pq.as_str() != "/" && !pq.as_str().is_empty())
    {
        return None;
    }
    let host = authority.host().to_ascii_lowercase();
    Some(match authority.port_u16() {
        Some(port) if port != default_port => format!("{scheme}://{host}:{port}"),
        _ => format!("{scheme}://{host}"),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(guard: &Guard, path: &str, pairs: &[(HeaderName, &str)]) -> Result<Access, ApiError> {
        let mut headers = HeaderMap::new();
        for (name, value) in pairs {
            headers.insert(name.clone(), HeaderValue::from_str(value).unwrap());
        }
        guard.check(&headers, &path.parse().unwrap())
    }

    fn pinned() -> Guard {
        Guard::default().with_port(8787)
    }

    #[test]
    fn loopback_hosts_on_our_port_pass() {
        for host in ["127.0.0.1:8787", "localhost:8787", "LOCALHOST:8787"] {
            assert!(
                run(&pinned(), "/api/info", &[(header::HOST, host)]).is_ok(),
                "{host}"
            );
        }
        assert!(run(&pinned(), "/api/info", &[]).is_ok(), "no Host at all");
        // Without a known port any port is fine.
        assert!(run(&Guard::default(), "/", &[(header::HOST, "localhost:1")]).is_ok());
    }

    #[test]
    fn foreign_hosts_and_ports_are_rejected() {
        for host in [
            "evil.example",
            "attacker.example:8787",
            "127.0.0.1.evil.example",
            "localhost.evil.example:8787",
            "127.0.0.1:9999",
            "localhost",
            "127.0.0.1",
            "[::1]:8787",
            "user@127.0.0.1:8787",
            "",
        ] {
            let err = run(&pinned(), "/api/processes", &[(header::HOST, host)]).unwrap_err();
            assert_eq!(err.status(), StatusCode::FORBIDDEN, "{host}");
        }
        // Absolute-form request target with a foreign authority.
        assert!(run(&pinned(), "http://evil.example/api/info", &[]).is_err());
        assert!(run(&pinned(), "http://127.0.0.1:8787/api/info", &[]).is_ok());
    }

    #[test]
    fn origin_must_be_our_own_by_default() {
        let host = (header::HOST, "127.0.0.1:8787");
        let check = |o| run(&pinned(), "/api/info", &[host.clone(), (header::ORIGIN, o)]);
        assert_eq!(check("http://127.0.0.1:8787"), Ok(Access::SameOrigin));
        assert_eq!(check("http://localhost:8787"), Ok(Access::SameOrigin));
        for bad in [
            "http://localhost:3000",
            "https://127.0.0.1:8787",
            "https://evil.example",
            "http://evil.example:8787",
            "null",
            "*",
            "file://localhost",
        ] {
            assert!(check(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn allow_listed_origins_get_cors() {
        let guard = pinned()
            .with_allowed_origins(["https://Tool.Example:443/", "http://localhost:3000"])
            .unwrap();
        assert_eq!(
            guard.allowed_origins(),
            ["https://tool.example", "http://localhost:3000"]
        );
        let host = (header::HOST, "127.0.0.1:8787");
        let check = |o: &str| {
            run(
                &guard,
                "/api/read",
                &[
                    host.clone(),
                    (header::ORIGIN, o),
                    (SEC_FETCH_SITE, "cross-site"),
                ],
            )
        };
        assert!(matches!(check("https://tool.example"), Ok(Access::Cors(_))));
        assert!(matches!(
            check("http://localhost:3000"),
            Ok(Access::Cors(_))
        ));
        assert!(check("https://other.example").is_err());
        assert!(check("http://tool.example").is_err());
        // An allow-listed origin does not relax the Host check.
        assert!(
            run(
                &guard,
                "/api/read",
                &[
                    (header::HOST, "tool.example"),
                    (header::ORIGIN, "https://tool.example")
                ]
            )
            .is_err()
        );
    }

    #[test]
    fn allow_list_rejects_wildcards_and_non_origins() {
        for bad in [
            "*",
            "null",
            "https://*.example.com",
            "https://tool.example/path",
            "https://tool.example?x=1",
            "ftp://tool.example",
            "tool.example",
            "https://user@tool.example",
            "",
        ] {
            assert!(
                Guard::default().with_allowed_origins([bad]).is_err(),
                "{bad}"
            );
        }
    }

    #[test]
    fn sec_fetch_site_guards_api_only() {
        let host = (header::HOST, "127.0.0.1:8787");
        let site = |path, v| run(&pinned(), path, &[host.clone(), (SEC_FETCH_SITE, v)]).is_ok();
        assert!(site("/api/search", "same-origin"));
        assert!(site("/api/search", "none"));
        assert!(!site("/api/search", "cross-site"));
        assert!(!site("/api/read", "same-site"));
        // Following a link to the UI from another site is fine.
        assert!(site("/", "cross-site"));
    }
}
